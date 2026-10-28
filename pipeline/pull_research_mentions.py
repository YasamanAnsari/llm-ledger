"""Harvest arXiv titles and abstracts in five AI categories over OAI-PMH and
record which ledger models and families they name.

Usage:
    python pipeline/pull_research_mentions.py              # daily: resume
    python pipeline/pull_research_mentions.py 2023-01-01   # backfill from a datestamp

Writes data/observations/research_mentions.csv, one row per (paper version,
model or family) named. Matching is deterministic: the text is tokenized
and compared, longest form first, with the ledger's own spellings (model
names, Epoch and Hub ids, vendor API ids, `text_surface_forms`, family
names). arXivRaw carries the latest version's text only, so a row is dated
by that version (`submitted`), never by v1.

Rows are checkpointed by (arxiv_id, version): a re-read of the same version
replaces its rows, a new version adds its own and older versions stay.
data/staging/research_harvest.json holds the datestamp range harvested.
arXiv metadata is CC0 1.0.
"""

from __future__ import annotations

import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch
import schema

OAI = "https://oaipmh.arxiv.org/oai"
SETS = ("cs:cs:AI", "cs:cs:CL", "cs:cs:CV", "cs:cs:LG", "stat:stat:ML")
OAI_NS = "{http://www.openarchives.org/OAI/2.0/}"
RAW_NS = "{http://arxiv.org/OAI/arXivRaw/}"
STATE_PATH = schema.STAGING_DIR / "research_harvest.json"

REQUEST_GAP_SECONDS = 3.1
RETRY_LIMIT = 5
# ponytail: a model added to the ledger after its papers were read is only
# matched within this window. Upgrade: keep a local corpus and re-match.
LOOKBACK_DAYS = 30
# Identity namespaces whose identifiers are spellings people write.
FORM_NAMESPACES = {"epoch", "huggingface", "openai_api", "anthropic_api", "google_api",
                   "mistral_api"}
TOKEN_RE = re.compile(r"[a-z]+|[0-9]+(?:\.[0-9]+)*[a-z]*", re.IGNORECASE)
# What may sit between the tokens of one spelling: "Llama 3.1-70B",
# "Llama~3.3", "gemma3:27b". Punctuation and markup ("step, (3", "phi^{4")
# break a spelling.
GAP_RE = re.compile(r"[ \-_~]{0,3}|:")
BARE_NUMBER = re.compile(r"[0-9.]+")


def tokenize(text: str) -> list:
    """[(token, start, end)] over lower-cased text; letter runs and number
    runs split, so "Llama3.1", "Llama-3.1" and "Llama 3.1" agree."""
    return [(m.group().lower(), m.start(), m.end()) for m in TOKEN_RE.finditer(text)]


def _usable(tokens: tuple) -> bool:
    # ponytail: bare names ("Qwen", "Claude", "GLM", "Phi") collide with
    # ordinary terms (generalized linear model, Claude Shannon) and are
    # skipped; a form needs a version or size. Upgrade: full-text
    # classification of mention type (plan step 2).
    return any(t[0].isdigit() for t in tokens) and sum(len(t) for t in tokens) >= 4


def form_index(models: list, crosswalk: list) -> dict:
    """First token -> [(tokens, model_id, family)], longest first.

    A spelling an identity source gives one model names that model. A
    family name, or a `text_surface_forms` spelling equal to one, names
    the family (`model_id` blank): those spellings are pinned to one
    representative model and say nothing about which checkpoint a paper
    used. A spelling claimed by models of different families is dropped.
    """
    family_of = {m["model_id"]: m["family"] for m in models}
    identity: dict = {}
    for m in models:
        identity.setdefault(tuple(t for t, _, _ in tokenize(m["canonical_name"])), set()).add(m["model_id"])
    for r in crosswalk:
        if r["namespace"] in FORM_NAMESPACES and r["model_id"] in family_of:
            name = r["identifier"].rsplit("/", 1)[-1]
            identity.setdefault(tuple(t for t, _, _ in tokenize(name)), set()).add(r["model_id"])
    # "Llama 3.1" and "Llama-3.1" both occur as family values; spellings
    # that tokenize alike are one family, named by its commonest spelling.
    families: dict = {}
    for m in models:
        if m["family"]:
            families.setdefault(tuple(t for t, _, _ in tokenize(m["family"])), Counter())[m["family"]] += 1
    text_forms: dict = {}
    for r in crosswalk:
        if r["namespace"] == "text_surface_forms" and r["model_id"] in family_of:
            text_forms.setdefault(tuple(t for t, _, _ in tokenize(r["identifier"])), set()).add(r["model_id"])

    resolved: dict = {}
    for tokens, names in families.items():
        resolved[tokens] = ("", max(names, key=lambda n: (names[n], n)))
    for tokens, ids in text_forms.items():
        if tokens not in resolved and len(ids) == 1:
            mid = next(iter(ids))
            resolved[tokens] = (mid, family_of[mid])
    for tokens, ids in identity.items():
        if len(ids) == 1:
            mid = next(iter(ids))
            resolved[tokens] = (mid, family_of[mid])
        elif len({family_of[i] for i in ids}) == 1:
            resolved[tokens] = ("", family_of[next(iter(ids))])
        else:
            resolved.pop(tokens, None)

    index: dict = {}
    for tokens, (mid, family) in resolved.items():
        if tokens and family and _usable(tokens):
            index.setdefault(tokens[0], []).append((tokens, mid, family))
    for forms in index.values():
        forms.sort(key=lambda f: -len(f[0]))
    return index


def _spelled(text: str, toks: list, i: int, tokens: tuple) -> bool:
    """Whether the tokens from i read as one written name in `text`."""
    end = i + len(tokens)
    gaps = [text[toks[k][2]:toks[k + 1][1]] for k in range(i, end - 1)]
    if not all(GAP_RE.fullmatch(g) for g in gaps):
        return False
    # ponytail: a word, a space and a bare number is prose ("step 3",
    # "seed 2") unless capitalised; capitalised prose ("Step 3") still
    # matches. Upgrade: full-text classification of mention type.
    if (len(tokens) > 1 and tokens[0].isalpha() and BARE_NUMBER.fullmatch(tokens[1])
            and any(c in gaps[0] for c in " ~")):
        return text[toks[i][1]].isupper()
    return True


def mentions(text: str, index: dict) -> list:
    """[(model_id, family, matched_text)], one per model or family named,
    first occurrence; longest form wins and matches do not overlap."""
    toks = tokenize(text)
    words = [t for t, _, _ in toks]
    found: dict = {}
    i = 0
    while i < len(toks):
        for tokens, mid, family in index.get(words[i], ()):
            if tuple(words[i:i + len(tokens)]) == tokens and _spelled(text, toks, i, tokens):
                found.setdefault((mid, family), text[toks[i][1]:toks[i + len(tokens) - 1][2]])
                i += len(tokens)
                break
        else:
            i += 1
    return [(mid, family, matched) for (mid, family), matched in found.items()]


def parse_page(payload: bytes) -> tuple:
    """(records, resumption token or "") from one ListRecords response.
    A record is (arxiv_id, version, submitted, title, abstract) for the
    latest version; deleted records are skipped."""
    root = ET.fromstring(payload)
    error = root.find(f"{OAI_NS}error")
    if error is not None:
        if error.get("code") == "noRecordsMatch":
            return [], ""
        raise RuntimeError(f"OAI-PMH error {error.get('code')}: {error.text}")
    records = []
    for rec in root.iter(f"{OAI_NS}record"):
        header = rec.find(f"{OAI_NS}header")
        raw = rec.find(f"{OAI_NS}metadata/{RAW_NS}arXivRaw")
        if header.get("status") == "deleted" or raw is None:
            continue
        versions = raw.findall(f"{RAW_NS}version")
        if not versions:
            raise ValueError(f"arXivRaw record {raw.findtext(f'{RAW_NS}id')} has no version")
        latest = versions[-1]
        submitted = parsedate_to_datetime(latest.findtext(f"{RAW_NS}date")).date().isoformat()
        records.append((raw.findtext(f"{RAW_NS}id"), latest.get("version"), submitted,
                        " ".join(raw.findtext(f"{RAW_NS}title", "").split()),
                        " ".join(raw.findtext(f"{RAW_NS}abstract", "").split())))
    token = root.find(f".//{OAI_NS}resumptionToken")
    return records, (token.text or "").strip() if token is not None else ""


def _get(params: dict) -> bytes:
    for _ in range(RETRY_LIMIT):
        time.sleep(REQUEST_GAP_SECONDS)
        try:
            return fetch.get_bytes(requests.Request("GET", OAI, params=params).prepare().url)
        except requests.HTTPError as exc:
            if exc.response.status_code != 503:
                raise
            time.sleep(int(exc.response.headers.get("Retry-After", "30")))
    raise RuntimeError(f"OAI-PMH still busy after {RETRY_LIMIT} tries: {params}")


def harvest(set_spec: str, start: date, end: date, get=_get):
    """Yield records with a datestamp in [start, end] for one set."""
    params = {"verb": "ListRecords", "set": set_spec, "metadataPrefix": "arXivRaw",
              "from": start.isoformat(), "until": end.isoformat()}
    while True:
        records, token = parse_page(get(params))
        yield from records
        if not token:
            return
        params = {"verb": "ListRecords", "resumptionToken": token}


def mention_rows(records: dict, index: dict) -> list:
    """Rows for {arxiv_id: record}; title and abstract are read together."""
    rows = []
    for arxiv_id, version, submitted, title, abstract in records.values():
        for mid, family, matched in mentions(f"{title}\n{abstract}", index):
            rows.append({"model_id": mid, "family": family, "arxiv_id": arxiv_id,
                         "version": version, "submitted": submitted, "matched_text": matched,
                         "match_type": "model" if mid else "family", "source": "abstract"})
    return rows


def merge(existing: list, fresh: list, reread: set, model_ids: set) -> list:
    """Replace the rows of every (arxiv_id, version) read again; drop rows
    naming a model the ledger no longer holds (its spelling went with it)."""
    kept = [r for r in existing if (r["arxiv_id"], r["version"]) not in reread]
    return [r for r in kept + fresh if not r["model_id"] or r["model_id"] in model_ids]


def _windows(start: date, end: date) -> list:
    out = []
    while start <= end:
        nxt = min(date(start.year + start.month // 12, start.month % 12 + 1, 1) - timedelta(days=1), end)
        out.append((start, nxt))
        start = nxt + timedelta(days=1)
    return out


def main() -> int:
    today = date.today()
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else None
    if len(sys.argv) == 2:
        start = date.fromisoformat(sys.argv[1])
        state = {"harvested_from": min(start.isoformat(), (state or {}).get("harvested_from", start.isoformat())),
                 "harvested_through": (state or {}).get("harvested_through", "")}
    elif len(sys.argv) == 1 and state:
        start = date.fromisoformat(state["harvested_through"]) - timedelta(days=LOOKBACK_DAYS)
    else:
        print(__doc__)
        return 2

    models = schema.read_table(schema.MODELS)
    index = form_index(models, schema.read_table(schema.CROSSWALK))
    model_ids = {m["model_id"] for m in models}
    path = schema.OBSERVATIONS_DIR / schema.RESEARCH_MENTIONS.filename
    rows = schema.read_table(schema.RESEARCH_MENTIONS, schema.OBSERVATIONS_DIR) if path.exists() else []
    for lo, hi in _windows(start, today):
        records = {}
        for set_spec in SETS:
            for rec in harvest(set_spec, lo, hi):
                records[rec[0]] = rec
        fresh = mention_rows(records, index)
        rows = merge(rows, fresh, {(r[0], r[1]) for r in records.values()}, model_ids)
        schema.write_table(schema.RESEARCH_MENTIONS, rows, schema.OBSERVATIONS_DIR)
        state["harvested_through"] = max(hi.isoformat(), state["harvested_through"])
        STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        print(f"pull_research_mentions: {lo}..{hi}: {len(records)} papers, "
              f"{len(fresh)} mention rows; {len(rows)} on record", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
