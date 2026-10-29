"""Citation counts for the arXiv paper behind each ledger model, from
OpenAlex (CC0) and Semantic Scholar (attribution: "Semantic Scholar").

A model's paper is, in this order: the arXiv paper of its own
`paper_published` event; else the arXiv link Epoch AI gives for the model
(through the crosswalk's `epoch` names); else the one arXiv paper its Hub
repos tag, when they tag exactly one (a card citing several is left out).
`linked_by` says which. Only ids and counts are kept, never paper text.

OpenAlex states the total (`cited_by_count`) and citations by citing
year (`counts_by_year`); Semantic Scholar states a total. The sources
count differently (OpenAlex keeps an arXiv preprint apart from its journal
version), so neither is corrected toward the other. A paper a source does
not know has no row from it. Each run rewrites
data/observations/citation_observations.csv and the crosswalk's `openalex`
and `semantic_scholar` rows.

Usage:
    python pipeline/pull_citations.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch
import schema

ARXIV = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})")
ARXIV_TAG = re.compile(r"(?:^|\|)arxiv:(\d{4}\.\d{4,5})(?=\||$)")
OPENALEX = "https://api.openalex.org/works"
S2_BATCH = "https://api.semanticscholar.org/graph/v1/paper/batch"
S2_FIELDS = "paperId,citationCount,externalIds"
OPENALEX_CHUNK, S2_CHUNK = 50, 500
NAMESPACES = ("openalex", "semantic_scholar")


def model_papers(events: list, crosswalk: list, epoch_links: dict, hub_tags: dict) -> list:
    """(model_id, arxiv_id, linked_by) for every model with a paper.
    `epoch_links` maps an Epoch model name to its link; `hub_tags` a Hub
    repo id to its pipe-joined tags."""
    by_event: dict = {}
    for e in events:
        found = ARXIV.search(e["source_url"])
        if e["event_type"] == "paper_published" and found:
            by_event.setdefault(e["model_id"], set()).add(found[1])
    by_epoch: dict = {}
    by_hub: dict = {}
    for r in crosswalk:
        if r["namespace"] == "epoch":
            found = ARXIV.search(epoch_links.get(r["identifier"], ""))
            if found:
                by_epoch.setdefault(r["model_id"], set()).add(found[1])
        elif r["namespace"] == "huggingface" and r["identifier"] in hub_tags:
            by_hub.setdefault(r["model_id"], set()).update(ARXIV_TAG.findall(hub_tags[r["identifier"]]))
    out = []
    for model_id in sorted(set(by_event) | set(by_epoch) | set(by_hub)):
        for linked_by, papers in (("paper_published_event", by_event.get(model_id)),
                                  ("epoch_link", by_epoch.get(model_id)),
                                  ("hf_card_arxiv_tag", by_hub.get(model_id))):
            if papers and (linked_by != "hf_card_arxiv_tag" or len(papers) == 1):
                out += [(model_id, paper, linked_by) for paper in sorted(papers)]
                break
    return out


def _doi(arxiv_id: str) -> str:
    return f"10.48550/arxiv.{arxiv_id}"


def fetch_openalex(arxiv_ids: list) -> list:
    works = []
    for i in range(0, len(arxiv_ids), OPENALEX_CHUNK):
        chunk = arxiv_ids[i:i + OPENALEX_CHUNK]
        response = requests.get(OPENALEX, timeout=fetch.TIMEOUT_SECONDS, headers={
            "User-Agent": fetch.USER_AGENT}, params={
            "filter": "doi:" + "|".join(_doi(a) for a in chunk), "per-page": OPENALEX_CHUNK,
            "select": "id,doi,cited_by_count,counts_by_year"})
        response.raise_for_status()
        works += response.json()["results"]
        time.sleep(1)
    return works


def fetch_semantic_scholar(arxiv_ids: list) -> list:
    papers = []
    for i in range(0, len(arxiv_ids), S2_CHUNK):
        chunk = arxiv_ids[i:i + S2_CHUNK]
        for attempt in range(4):
            response = requests.post(S2_BATCH, params={"fields": S2_FIELDS},
                                     json={"ids": [f"ARXIV:{a}" for a in chunk]},
                                     headers={"User-Agent": fetch.USER_AGENT},
                                     timeout=fetch.TIMEOUT_SECONDS)
            if response.status_code != 429:
                break
            time.sleep(10 * (attempt + 1))  # the keyless pool is shared and throttles
        response.raise_for_status()
        papers += [p for p in response.json() if p]
    return papers


def citation_rows(papers: list, openalex: list, s2: list, observed_on: str) -> tuple:
    """(citation rows, crosswalk rows) from the model-paper links and the
    two sources' records; counts are copied as stated."""
    alex = {w["doi"].removeprefix("https://doi.org/10.48550/arxiv.").lower(): w
            for w in openalex if w.get("doi")}
    sem = {p["externalIds"]["ArXiv"]: p for p in s2 if (p.get("externalIds") or {}).get("ArXiv")}
    rows, links = [], []
    for model_id, arxiv_id, linked_by in papers:
        base = {"model_id": model_id, "arxiv_id": arxiv_id, "linked_by": linked_by,
                "observed_on": observed_on}
        work = alex.get(arxiv_id.lower())
        if work:
            work_id = work["id"].removeprefix("https://openalex.org/")
            url = f"{OPENALEX}/{work_id}"
            rows.append(base | {"source": "openalex", "work_id": work_id, "year": "",
                                "citations": str(work["cited_by_count"]), "source_url": url})
            rows += [base | {"source": "openalex", "work_id": work_id, "year": str(c["year"]),
                             "citations": str(c["cited_by_count"]), "source_url": url}
                     for c in work["counts_by_year"]]
            links.append({"model_id": model_id, "namespace": "openalex", "identifier": work_id})
        paper = sem.get(arxiv_id)
        if paper:
            rows.append(base | {"source": "semantic_scholar", "work_id": paper["paperId"], "year": "",
                                "citations": str(paper["citationCount"]),
                                "source_url": f"https://www.semanticscholar.org/paper/{paper['paperId']}"})
            links.append({"model_id": model_id, "namespace": "semantic_scholar",
                          "identifier": paper["paperId"]})
    return rows, links


def _hub_tags() -> dict:
    path = schema.snapshot_file("hf", "normalized.csv", max_age_days=None)
    with path.open(newline="", encoding="utf-8") as fh:
        return {r["repo_id"]: r["tags"] for r in csv.DictReader(fh)}


def _epoch_links() -> dict:
    path = schema.snapshot_file("epoch", "normalized.csv", max_age_days=None)
    with path.open(newline="", encoding="utf-8") as fh:
        return {r["model"]: r["link"] for r in csv.DictReader(fh)}


def main() -> int:
    crosswalk = schema.read_table(schema.CROSSWALK)
    papers = model_papers(schema.read_table(schema.EVENTS), crosswalk, _epoch_links(), _hub_tags())
    arxiv_ids = sorted({p for _, p, _ in papers})
    openalex = fetch_openalex(arxiv_ids)
    s2 = fetch_semantic_scholar(arxiv_ids)
    for source, records in (("openalex", openalex), ("semantic_scholar", s2)):
        schema.write_snapshot(source, "works.json", json.dumps(records, sort_keys=True).encode(),
                              OPENALEX if source == "openalex" else S2_BATCH)
    rows, links = citation_rows(papers, openalex, s2, schema.today_utc())
    schema.write_table(schema.CITATION_OBSERVATIONS, rows, schema.OBSERVATIONS_DIR)
    kept = [r for r in crosswalk if r["namespace"] not in NAMESPACES]
    schema.write_table(schema.CROSSWALK, kept + links)
    found = {source: len({r["arxiv_id"] for r in rows if r["source"] == source}) for source in NAMESPACES}
    print(f"citations: {len(papers)} model-paper links, {len(arxiv_ids)} papers; "
          f"OpenAlex knows {found['openalex']}, Semantic Scholar {found['semantic_scholar']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
