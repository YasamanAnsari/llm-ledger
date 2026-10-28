"""Look up arXiv v1 submission dates (the only date paper_published accepts).

Usage:
    python pipeline/pull_arxiv.py                     # daily sweep: paper leads
    python pipeline/pull_arxiv.py 2303.08774          # by arXiv id
    python pipeline/pull_arxiv.py "GPT-4 Technical Report"   # by title search

The sweep searches arXiv titles for model families with no
`paper_published` event and queues `paper_lead` review rows for titles
that name the family as their subject ("Gemma 3 Technical Report",
"Kimi K2: Open Agentic Intelligence"), submitted near the family's first
release. A person picks the model and writes the event; a paper about a
family is not attributed to one checkpoint by machine.
"""

from __future__ import annotations

import csv
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch
import schema

API = "http://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"

ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")

# arXiv asks API clients for one request every three seconds.
REQUEST_GAP_SECONDS = 3.1
# ponytail: a fixed per-run budget rotated by day; a family is re-asked
# every len(families)/MAX_QUERIES days. Upgrade: checkpoint asked families.
MAX_QUERIES = 40
# A report lands before or after the release; a title match years away is
# another model of the same name.
WINDOW_BEFORE, WINDOW_AFTER = timedelta(days=180), timedelta(days=365)


def _entries(query: str) -> list:
    if ARXIV_ID_RE.match(query):
        url = f"{API}?id_list={query.split('v')[0]}&max_results=1"
    else:
        quoted = urllib.parse.quote(f'ti:"{query}"')
        url = f"{API}?search_query={quoted}&max_results=5"
    root = ET.fromstring(fetch.get_bytes(url))
    return root.findall(f"{ATOM}entry")


def v1_dates(query: str) -> list:
    """[(arxiv_id, title, v1_published_date)] for matching papers.

    arXiv's Atom `published` element is always the v1 submission timestamp
    (later revisions only change `updated`), so it is safe as-is.
    """
    results = []
    for entry in _entries(query):
        raw_id = entry.findtext(f"{ATOM}id", "")
        arxiv_id = raw_id.rsplit("/abs/", 1)[-1]
        title = " ".join((entry.findtext(f"{ATOM}title") or "").split())
        published = (entry.findtext(f"{ATOM}published") or "")[:10]
        if arxiv_id and published:
            results.append((arxiv_id, title, published))
    return results


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-]+", "-", text.strip().lower())


def names_family(title: str, family: str) -> bool:
    """True when the title is about the family itself: the family name
    alone, or followed by a colon or "technical report"."""
    t, f = _norm(title), _norm(family)
    return t == f or t.startswith(f + ":") or t.startswith(f + "-technical-report") \
        or t.startswith(f + "-report")


def families_without_paper(models: list, events: list) -> list:
    """[(developer_org_id, family, earliest first availability, model ids)]
    for dated families with no `paper_published` event on any member."""
    with_paper = {e["model_id"] for e in events if e["event_type"] == "paper_published"}
    groups: dict = {}
    for m in models:
        if m["family"] and m["first_public_availability_date"]:
            groups.setdefault((m["developer_org_id"], m["family"]), []).append(m)
    return sorted(
        (org, family, min(m["first_public_availability_date"] for m in members),
         sorted(m["model_id"] for m in members))
        for (org, family), members in groups.items()
        if not any(m["model_id"] in with_paper for m in members))


def paper_leads(families: list, search) -> list:
    """Review rows for the titles `search(family)` returns that name the
    family and were submitted inside the release window."""
    rows = []
    for org, family, released, members in families:
        day = date.fromisoformat(released)
        for arxiv_id, title, published in search(family):
            if not names_family(title, family):
                continue
            if not day - WINDOW_BEFORE <= date.fromisoformat(published) <= day + WINDOW_AFTER:
                continue
            unversioned = re.sub(r"v\d+$", "", arxiv_id)
            rows.append({
                "kind": "paper_lead", "left_source": "ledger", "left_key": f"{org}/{family}",
                "right_source": "arxiv", "right_key": f"https://arxiv.org/abs/{unversioned}",
                "score": "",
                "note": f"v1 {published} '{title}'; family first available {released}; "
                        f"members: {', '.join(members[:6])}"
                        + (" ..." if len(members) > 6 else "")
                        + "; add paper_published to the model the paper describes, or reject",
            })
    return rows


def _queued_families() -> set:
    path = schema.STAGING_DIR / "review_queue.csv"
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as fh:
        return {r["left_key"] for r in csv.DictReader(fh) if r["kind"] == "paper_lead"}


def sweep(today: date) -> int:
    families = families_without_paper(schema.read_table(schema.MODELS),
                                      schema.read_table(schema.EVENTS))
    queued = _queued_families() | {k[1] for k in schema.read_review_decisions()
                                   if k[0] == "paper_lead"}
    families = [f for f in families if f"{f[0]}/{f[1]}" not in queued]
    if not families:
        print("pull_arxiv: no family left to search")
        return 0
    start = today.toordinal() * MAX_QUERIES % len(families)
    batch = (families[start:] + families[:start])[:MAX_QUERIES]

    def search(family: str) -> list:
        time.sleep(REQUEST_GAP_SECONDS)
        return v1_dates(family)

    rows = paper_leads(batch, search)
    schema.merge_review_queue(rows)
    print(f"pull_arxiv: searched {len(batch)} of {len(families)} families without a paper; "
          f"{len(rows)} paper lead(s) queued for review")
    return 0


def main() -> int:
    if len(sys.argv) == 1:
        return sweep(date.today())
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    matches = v1_dates(sys.argv[1])
    if not matches:
        print(f"pull_arxiv: no results for {sys.argv[1]!r}")
        return 1
    for arxiv_id, title, published in matches:
        print(f"{published}  https://arxiv.org/abs/{arxiv_id}  {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
