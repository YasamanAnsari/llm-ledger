"""Look up the first public Wayback capture of Hub repos whose weights date
rests only on repo creation.

Repo `createdAt` is a lower bound on the public release (repos are created
private). The first Internet Archive capture of the repo page is evidence
the repo was public by then. hf_census.py feeds both to the confidence
policy: creation within BOUND_AGREE_DAYS of the first capture verifies the
date; a wider gap keeps it inferred (crawl lag is common for small repos).

Only repos still `inferred` and without a Wayback claim are queried, oldest
first, at most MAX_QUERIES per run, one request per second. The Wayback
availability API asked for the capture "closest to 1996" returns the
earliest one, in about a second (the CDX index takes ~15 s per query).
Results are written to data/raw/wayback/<date>/normalized.csv; once merged
into claims.csv they persist, so each repo is queried once.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests

import fetch
import schema
from confidence import group_claims

AVAILABILITY = "https://archive.org/wayback/available"
MAX_QUERIES = 150
PACE_SECONDS = 2      # 1 req/s drew HTTP 429s from archive.org
BACKOFF_SECONDS = 15
COLUMNS = ["repo_id", "first_capture_date", "first_capture_timestamp"]


def first_capture(repo_id: str) -> str:
    """YYYYMMDDhhmmss of the earliest HTTP-200 capture, or "" when none."""
    payload = json.loads(fetch.get_bytes(
        f"{AVAILABILITY}?url=huggingface.co/{repo_id}&timestamp=19960101"))
    closest = payload.get("archived_snapshots", {}).get("closest") or {}
    return closest.get("timestamp", "") if str(closest.get("status")) == "200" else ""


def pending_repos(tables: dict) -> list:
    claims_by_event = group_claims(tables["claims"])
    hf_repo_of = {}
    for row in tables["crosswalk"]:
        if row["namespace"] == "huggingface":
            hf_repo_of.setdefault(row["model_id"], row["identifier"])
    todo = []
    for e in tables["events"]:
        if e["event_type"] != "weights_released" or e["source_type"] != "hf_hub":
            continue
        if e["confidence"] == "verified":
            continue
        if any("web.archive.org" in c["source_url"] for c in claims_by_event.get(e["event_id"], [])):
            continue
        repo_id = e["source_url"].removeprefix("https://huggingface.co/") or hf_repo_of.get(e["model_id"])
        if repo_id:
            todo.append((e["date"], repo_id))
    return [repo for _, repo in sorted(todo)][:MAX_QUERIES]


def main() -> int:
    repos = pending_repos(schema.load_core())
    rows, failures = [], 0
    for i, repo_id in enumerate(repos):
        if i:
            time.sleep(PACE_SECONDS)
        try:
            try:
                stamp = first_capture(repo_id)
            except requests.HTTPError as exc:
                if exc.response is None or exc.response.status_code != 429:
                    raise
                time.sleep(BACKOFF_SECONDS)  # archive.org rate limit: one retry
                stamp = first_capture(repo_id)
        except Exception as exc:  # one archive.org hiccup must not lose the batch
            failures += 1
            print(f"pull_wayback: WARN {repo_id}: {exc}")
            continue
        rows.append({
            "repo_id": repo_id,
            "first_capture_date": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}" if len(stamp) >= 8 else "",
            "first_capture_timestamp": stamp,
        })
    out = schema.snapshot_dir("wayback") / "normalized.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    captured = sum(1 for r in rows if r["first_capture_date"])
    print(f"pull_wayback: {len(repos)} repos queried, {captured} captured, "
          f"{len(rows) - captured} never archived, {failures} failed -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
