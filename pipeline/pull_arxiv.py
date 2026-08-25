"""Look up arXiv v1 submission dates (the only date paper_published accepts).

Usage:
    python pipeline/pull_arxiv.py 2303.08774          # by arXiv id
    python pipeline/pull_arxiv.py "GPT-4 Technical Report"   # by title search
"""

from __future__ import annotations

import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch

API = "http://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"

ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")


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


def main() -> int:
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
