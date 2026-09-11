"""Name normalization and cross-source matching (crosswalk builder).

Joins the latest models.dev, OpenRouter, and Epoch snapshots on normalized
model names. Exact/variant matches join directly; fuzzy candidates are
auto-accepted at rapidfuzz ratio >= 97, queued for manual review in the
92-97 band, and discarded below 92 (a poisoned crosswalk is worse than a
missing match). A queued pair a person has accepted in
data/staging/review_decisions.csv joins with method `reviewed`; a rejected
or dismissed one is never queued again.

Outputs:
    data/generated/matched_models.csv   one row per matched cluster
    data/staging/review_queue.csv       fuzzy candidates awaiting a human
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

from rapidfuzz import fuzz, process

sys.path.insert(0, str(Path(__file__).resolve().parent))

import orgs_seed
import schema

AUTO_ACCEPT = 97.0
QUEUE_FLOOR = 92.0

MATCHED_COLUMNS = [
    "match_key", "sources", "match_method", "vendor_prefix",
    "or_prefix", "md_prefix",
    "md_provider", "md_model_key", "md_release_date", "md_provider_count",
    "md_open_weights", "md_release_dates", "md_open_weights_votes",
    "md_modalities_in", "md_modalities_out",
    "md_context_length", "md_max_output_tokens", "md_cost_input",
    "md_cost_output", "md_cost_cache_read", "md_reasoning", "md_tool_call",
    "md_knowledge_cutoff", "md_snapshot_date",
    "or_id", "or_created", "or_expiration",
    "epoch_model", "epoch_organization", "epoch_publication_date",
    "epoch_confidence",
]

# Leading org tokens that are naming noise, not family names.
PREFIX_REWRITES = (
    ("meta-llama-", "llama-"),
    ("deepseek-ai-", "deepseek-"),
    ("moonshotai-", "kimi-"),
    ("google-", ""),
    ("openai-", ""),
    ("anthropic-", ""),
    ("mistralai-", ""),
    ("z-ai-", ""),
    ("zhipu-", ""),
    ("01-ai-", ""),
    ("xai-", ""),
)

# Role suffixes distinguish checkpoints (base vs instruct) and are kept for
# identity; they are stripped only when matching against catalogs that name
# a family without a role (Epoch).
ROLE_SUFFIXES = ("-instruct", "-chat", "-it")

# Trailing tokens that name a packaging of the same weights, not a model:
# quantizations, dtypes, framework conversions. Stripped from the identity
# key and recorded as `format_suffix`.
FORMAT_TOKENS = {
    "fp8", "fp16", "bf16", "fp4", "nvfp4", "mxfp4", "mxfp8", "int4", "int8",
    "w4a16", "w8a8", "w4afp8", "w4a8c8", "2bits", "4bits", "8bits", "4bit",
    "8bit", "tp2", "tp4", "tp8", "hf", "pth", "paddle", "safetensors",
}

# Date-like suffixes marking a dated snapshot of an alias.
DATE_SUFFIX_RE = re.compile(r"-(20\d{2}-?\d{2}-?\d{2}|20\d{6})$")
MMDD_SUFFIX_RE = re.compile(r"-(0[1-9]|1[0-2])([0-2]\d|3[01])$")

# Catalog ids that are moving pointers, not checkpoints.
ALIAS_TOKENS = {"latest"}
ALIAS_KEYS = {"deepseek-chat", "deepseek-reasoner", "gemini-exp", "chatgpt-4o-latest"}
# Products this ledger does not track: embeddings, rerankers, speech
# utilities, moderation and reward models, protein models, and image /
# video / music generators named as such. Modalities alone cannot tell an
# image generator from a language model that also emits images, so the
# generator families are named here.
OUT_OF_SCOPE_RE = re.compile(
    r"(^|-)(embed|embedding|embeddings|rerank|tts|transcribe|transcription|"
    r"moderation|reward|esm\d*|visionreward|image|imagen|dall-?e\d*|sora|veo\d*|"
    r"lyria|flux|kontext)(-|$)")


def is_alias_key(key: str) -> bool:
    """True for ids that point at whatever the vendor currently serves."""
    return key in ALIAS_KEYS or bool(ALIAS_TOKENS & set(key.split("-")))


def is_out_of_scope_key(key: str) -> bool:
    """True for names of products the ledger does not track."""
    return bool(OUT_OF_SCOPE_RE.search(key))


def normalize_name(raw: str) -> dict:
    """Normalize a model identifier to a match key.

    Returns {key, prefix, snapshot_suffix, format_suffix}: the vendor prefix
    (before '/'), any date suffix and any packaging suffix are preserved as
    metadata. A date suffix marks a dated snapshot candidate; a packaging
    suffix (FP8, BF16, INT4, HF conversion) marks the same weights in
    another container, never a distinct model.
    """
    text = raw.strip().lower()
    prefix = ""
    if "/" in text:
        prefix, text = text.split("/", 1)
    text = text.split(":", 1)[0]  # OpenRouter serving variants (:free, :batch)
    text = re.sub(r"[\s_.()\[\]]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")

    snapshot_suffix = ""
    m = DATE_SUFFIX_RE.search(text) or MMDD_SUFFIX_RE.search(text)
    if m:
        snapshot_suffix = m.group(0).lstrip("-")
        text = text[: m.start()]

    format_parts: list = []
    parts = text.split("-")
    while len(parts) > 1 and parts[-1] in FORMAT_TOKENS:
        format_parts.insert(0, parts.pop())
    text = "-".join(parts)

    for old, new in PREFIX_REWRITES:
        if text.startswith(old):
            text = new + text[len(old):]
            break
    return {"key": text, "prefix": prefix, "snapshot_suffix": snapshot_suffix,
            "format_suffix": "-".join(format_parts)}


def slug_for(key: str, org_id: str) -> str:
    """Ledger model_id for a normalized key.

    Very short keys (o3, r1, hy3...) get the org prefix, mirroring spec
    examples like `openai-o3`; longer keys are already self-identifying.
    Shared by reconcile and the HF census so both derive the same id.
    """
    if len(key) <= 4 and org_id and not key.startswith(org_id):
        return f"{org_id}-{key}"
    return key


def key_variants(key: str, identity: bool = False) -> list:
    """Spellings of one key, most specific first.

    Bridges the letter-digit boundary spelling split: vendors write
    "Qwen2.5-72B" (fused) while aggregators write "qwen-2.5-72b" (split),
    which normalize to different keys (qwen2-5-... vs qwen-2-5-...).
    With `identity=True` the role suffix stays: a base and its instruct
    checkpoint are different models. Without it, role-stripped variants are
    added for matching catalogs that name only the family (Epoch).
    """
    variants = [key]
    fused = re.sub(r"^([a-z]+)-(\d)", r"\1\2", key)
    split = re.sub(r"^([a-z]+)(\d)", r"\1-\2", key)
    for alt in (fused, split):
        if alt != key:
            variants.append(alt)
    if identity:
        return variants
    for suffix in ROLE_SUFFIXES:
        if key.endswith(suffix):
            variants.append(key[: -len(suffix)])
            for alt in (fused, split):
                if alt != key and alt.endswith(suffix):
                    variants.append(alt[: -len(suffix)])
    return variants


def _read_normalized(source: str) -> list:
    path = schema.snapshot_file(source, "normalized.csv")
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _votes(pairs: list) -> list:
    """(provider, value) pairs that carry a value; the unix epoch is
    models.dev's serialization of a missing date."""
    return [(p, v) for p, v in pairs if v and v != "1970-01-01"]


def stated_release(dates: list, org_id: str) -> tuple:
    """(date, basis) for a model's release date across models.dev providers.

    The vendor's own provider entry wins (`first_party`); else a strict
    majority of resellers (`majority`); a lone reseller counts (`single`);
    genuine disagreement yields no date at all ("", "") rather than a guess.
    """
    dated = _votes(dates)
    if not dated:
        return "", ""
    own = [d for p, d in dated if orgs_seed.resolve_org(p) == org_id]
    if own:
        return Counter(own).most_common(1)[0][0], "first_party"
    if len(dated) == 1:
        return dated[0][1], "single"
    counts = Counter(d for _, d in dated)
    date, n = counts.most_common(1)[0]
    if n * 2 > len(dated):
        return date, "majority"
    return "", ""


def majority_date(dates: list) -> str:
    """Strict-majority release date, else "" (for the disagreement report)."""
    dated = _votes(dates)
    if not dated:
        return ""
    date, n = Counter(d for _, d in dated).most_common(1)[0]
    return date if n * 2 > len(dated) else ""


def open_weights_vote(votes: list, org_id: str) -> bool:
    """Whether the weights are open: the vendor's own entry decides, else a
    strict majority of resellers; a tie is not evidence of open weights."""
    cast = [(p, v) for p, v in votes if v in ("true", "false")]
    own = [v for p, v in cast if orgs_seed.resolve_org(p) == org_id]
    if own:
        return Counter(own).most_common(1)[0][0] == "true"
    return sum(v == "true" for _, v in cast) * 2 > len(cast)


def serialize_votes(pairs: list) -> str:
    return "|".join(f"{p}:{v}" for p, v in sorted(pairs))


def parse_votes(text: str) -> list:
    return [tuple(item.rsplit(":", 1)) for item in text.split("|") if ":" in item]


def load_models_dev() -> dict:
    """Normalized key -> aggregated models.dev record.

    models.dev lists the same model under many reseller providers, each
    claiming a release date and an open-weights flag. Every vote is kept
    (`dates`, `ow_votes`) so reconcile can weigh them knowing the model's
    vendor; `release_date` is the strict majority for the disagreement
    report. The record whose provider matches the vendor prefix embedded in
    the model key supplies the serving metadata.
    """
    grouped: dict = {}
    for row in _read_normalized("models_dev"):
        norm = normalize_name(row["model_key"])
        if not norm["key"]:
            continue
        entry = grouped.setdefault(norm["key"], {"rows": [], "providers": set()})
        entry["rows"].append((norm, row))
        entry["providers"].add(row["provider"])

    result = {}
    for key, entry in grouped.items():
        dated = [(n, r) for n, r in entry["rows"] if r["release_date"]]
        pool = dated or entry["rows"]
        first_party = [
            (n, r) for n, r in pool
            if n["prefix"] and n["prefix"] in r["provider"]
        ] or pool
        norm, best = min(first_party, key=lambda item: item[1]["release_date"] or "9999")
        result[key] = {
            "norm": norm,
            "row": best,
            "release_date": majority_date([(r["provider"], r["release_date"]) for _, r in dated]),
            "provider_count": len(entry["providers"]),
            "dates": [(r["provider"], r["release_date"]) for _, r in entry["rows"]],
            "ow_votes": [(r["provider"], r["open_weights"]) for _, r in entry["rows"]],
        }
    return result


def load_openrouter() -> dict:
    """Normalized key -> earliest-created OpenRouter record."""
    result: dict = {}
    for row in _read_normalized("openrouter"):
        norm = normalize_name(row["id"])
        key = norm["key"]
        if not key:
            continue
        if key not in result or (row["created_date"] or "9999") < (result[key]["row"]["created_date"] or "9999"):
            result[key] = {"norm": norm, "row": row}
    return result


def load_epoch() -> dict:
    result: dict = {}
    for row in _read_normalized("epoch"):
        norm = normalize_name(row["model"])
        key = norm["key"]
        if key and key not in result:
            result[key] = {"norm": norm, "row": row}
    return result


def _variant_index(records: dict) -> dict:
    """variant key -> canonical key, most specific variant wins."""
    index = {}
    for key in records:
        for variant in key_variants(key):
            index.setdefault(variant, key)
    return index


def _fuzzy_pairs(left_keys: list, right_index: dict) -> list:
    """(left_key, right_key, score) for best fuzzy candidates >= QUEUE_FLOOR."""
    choices = list(right_index)
    pairs = []
    for key in left_keys:
        found = process.extractOne(
            key, choices, scorer=fuzz.ratio, score_cutoff=QUEUE_FLOOR
        )
        if found:
            pairs.append((key, right_index[found[0]], found[1]))
    return pairs


def apply_fuzzy_decision(decisions: dict, left: str, right: str) -> str:
    """A person's decision on a queued fuzzy pair: accept / reject /
    dismiss, or "" when nobody has ruled on it."""
    row = decisions.get(("fuzzy_match", left, right))
    return row["decision"] if row else ""


def _settle_fuzzy(unmatched: list, right_index: dict, decisions: dict,
                  left_source: str, right_source: str) -> tuple:
    """(joins, queue_rows) for keys that found no exact match.

    A pair joins when a person accepted it or the score clears AUTO_ACCEPT;
    a rejected or dismissed pair is dropped without being queued again;
    the 92-97 band waits in the review queue.
    """
    joins, queue = [], []
    for left, right, score in _fuzzy_pairs(unmatched, right_index):
        decision = apply_fuzzy_decision(decisions, left, right)
        if decision == "accept":
            joins.append((left, right, "reviewed"))
        elif decision:
            continue
        elif score >= AUTO_ACCEPT:
            joins.append((left, right, f"fuzzy:{score:.0f}"))
        else:
            queue.append({
                "kind": "fuzzy_match", "left_source": left_source, "left_key": left,
                "right_source": right_source, "right_key": right, "score": f"{score:.1f}",
                "note": "92-97 band: confirm or reject before crosswalking",
            })
    return joins, queue


def match(md: dict, orr: dict, epoch: dict, decisions: dict | None = None,
          md_snapshot: str = "") -> tuple:
    """Cluster the three catalogs. Returns (matched_rows, review_queue_rows).

    `md`, `orr`, `epoch` are the loaders' key -> record dicts; `decisions`
    is schema.read_review_decisions(); `md_snapshot` dates the models.dev
    metadata carried into the rows.
    """
    decisions = decisions or {}
    md_index = _variant_index(md)

    # cluster key (models.dev key when present) -> {"md":, "or":, "epoch":, "method":}
    clusters: dict = {}
    review_queue: list = []

    def cluster_for(key: str) -> dict:
        return clusters.setdefault(key, {"md": None, "or": None, "epoch": None, "methods": []})

    for key, record in md.items():
        cluster_for(key)["md"] = record

    # --- OpenRouter -> models.dev ---
    unmatched_or = []
    for key, record in orr.items():
        hit = next((md_index[v] for v in key_variants(key) if v in md_index), None)
        if hit:
            c = cluster_for(hit)
            c["or"] = record
            c["methods"].append("or:exact")
        else:
            unmatched_or.append(key)
    joins, queued = _settle_fuzzy(unmatched_or, md_index, decisions, "openrouter", "models_dev")
    review_queue += queued
    for left, right, how in joins:
        c = cluster_for(right)
        c["or"] = orr[left]
        c["methods"].append(f"or:{how}")
    matched_or = {id(c["or"]) for c in clusters.values() if c["or"]}
    for key, record in orr.items():
        if id(record) not in matched_or and key not in clusters:
            clusters[key] = {"md": None, "or": record, "epoch": None, "methods": ["or:only"]}

    # --- Epoch -> clusters (models.dev keys, then OpenRouter-only keys) ---
    cluster_index = _variant_index(clusters)
    unmatched_epoch = []
    for key, record in epoch.items():
        hit = next((cluster_index[v] for v in key_variants(key) if v in cluster_index), None)
        if hit:
            c = clusters[hit]
            c["epoch"] = record
            c["methods"].append("epoch:exact")
        else:
            unmatched_epoch.append(key)
    joins, queued = _settle_fuzzy(unmatched_epoch, cluster_index, decisions, "epoch", "ledger_cluster")
    review_queue += queued
    for left, right, how in joins:
        c = clusters[right]
        if c["epoch"] is None:
            c["epoch"] = epoch[left]
            c["methods"].append(f"epoch:{how}")

    rows = []
    for key in sorted(clusters):
        c = clusters[key]
        sources = [s for s, present in
                   (("models_dev", c["md"]), ("openrouter", c["or"]), ("epoch", c["epoch"]))
                   if present]
        md_rec, or_rec, ep_rec = c["md"], c["or"], c["epoch"]
        prefix = ""
        # OpenRouter's vendor namespace is curated (true developer); models.dev
        # keys often carry a hosting-provider or base-family prefix instead.
        for rec in (or_rec, md_rec):
            if rec and rec["norm"]["prefix"]:
                prefix = rec["norm"]["prefix"]
                break
        rows.append({
            "match_key": key,
            "sources": "|".join(sources),
            "match_method": "|".join(sorted(set(c["methods"]))) or "md:only",
            "vendor_prefix": prefix,
            "or_prefix": or_rec["norm"]["prefix"] if or_rec else "",
            "md_prefix": md_rec["norm"]["prefix"] if md_rec else "",
            "md_provider": md_rec["row"]["provider"] if md_rec else "",
            "md_model_key": md_rec["row"]["model_key"] if md_rec else "",
            "md_release_date": md_rec["release_date"] if md_rec else "",
            "md_provider_count": md_rec["provider_count"] if md_rec else "",
            "md_open_weights": md_rec["row"]["open_weights"] if md_rec else "",
            "md_release_dates": serialize_votes(md_rec["dates"]) if md_rec else "",
            "md_open_weights_votes": serialize_votes(md_rec["ow_votes"]) if md_rec else "",
            "md_modalities_in": md_rec["row"]["modalities_in"] if md_rec else "",
            "md_modalities_out": md_rec["row"]["modalities_out"] if md_rec else "",
            "md_context_length": md_rec["row"]["context_length"] if md_rec else "",
            "md_max_output_tokens": md_rec["row"]["max_output_tokens"] if md_rec else "",
            "md_cost_input": md_rec["row"]["cost_input"] if md_rec else "",
            "md_cost_output": md_rec["row"]["cost_output"] if md_rec else "",
            "md_cost_cache_read": md_rec["row"]["cost_cache_read"] if md_rec else "",
            "md_reasoning": md_rec["row"]["reasoning"] if md_rec else "",
            "md_tool_call": md_rec["row"]["tool_call"] if md_rec else "",
            "md_knowledge_cutoff": md_rec["row"]["knowledge_cutoff"] if md_rec else "",
            "md_snapshot_date": md_snapshot if md_rec else "",
            "or_id": or_rec["row"]["id"] if or_rec else "",
            "or_created": or_rec["row"]["created_date"] if or_rec else "",
            "or_expiration": or_rec["row"]["expiration_date"] if or_rec else "",
            "epoch_model": ep_rec["row"]["model"] if ep_rec else "",
            "epoch_organization": ep_rec["row"]["organization"] if ep_rec else "",
            "epoch_publication_date": ep_rec["row"]["publication_date"] if ep_rec else "",
            "epoch_confidence": ep_rec["row"]["confidence"] if ep_rec else "",
        })
    return rows, review_queue


def main() -> int:
    # Dated by content, not by pull day, so an unchanged catalog does not
    # rewrite every price_date in attributes.csv each morning.
    md_snapshot = schema.snapshot_content_date("models_dev", "api.json")
    rows, review_queue = match(load_models_dev(), load_openrouter(), load_epoch(),
                               schema.read_review_decisions(), md_snapshot)

    out = schema.GENERATED_DIR / "matched_models.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MATCHED_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    # The queue is shared: this script owns only kind=fuzzy_match rows.
    schema.merge_review_queue(review_queue, replace_kinds=("fuzzy_match",))

    multi = sum(1 for r in rows if "|" in r["sources"])
    print(f"match: {len(rows)} clusters, {multi} matched across >=2 sources, "
          f"{len(review_queue)} in review queue -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
