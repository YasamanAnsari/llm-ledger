"""Tier-3 discovery sweep over NHLOCAL/AiTimeline (CC BY 4.0).

Pulls the timeline data file, snapshots it raw, and queues *leads* for model
names not already in the ledger into data/staging/review_queue.csv. Leads are
never written to core: per methodology, community-timeline dates stay
unverified until confirmed against a primary source.

The file is a narrow, regular YAML subset (year / date / info.text), parsed
with a small line parser to avoid a yaml dependency.
"""
from __future__ import annotations

import csv
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch
import match as matchmod
import schema

TIMELINE_URL = "https://raw.githubusercontent.com/NHLOCAL/AiTimeline/main/_data/timeline.yml"
BOLD_RE = re.compile(r"<b>(.+?)</b>")
MONTHS = {m: i for i, m in enumerate(
    ("January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"), start=1)}

QUEUE_COLUMNS = ["kind", "left_source", "left_key", "right_source",
                 "right_key", "score", "note"]


def parse_timeline(text: str) -> list[dict]:
    """Yield {name, date, precision, context} for each <b>bolded</b> mention."""
    leads = []
    year = month = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- year:"):
            year = int(stripped.split(":", 1)[1])
            month = None
        elif stripped.startswith("- date:"):
            raw = stripped.split(":", 1)[1].strip()
            month = MONTHS.get(raw.split()[0]) if raw else None
        elif stripped.startswith("- text:") and year:
            body = stripped.split(":", 1)[1].strip()
            date = (f"{year}-{month:02d}-01", "month") if month else (f"{year}-01-01", "year")
            for name in BOLD_RE.findall(body):
                leads.append({
                    "name": name.strip(),
                    "date": date[0],
                    "precision": date[1],
                    "context": re.sub(r"</?b>", "", body)[:160],
                })
    return leads


def main() -> int:
    raw = fetch.get_bytes(TIMELINE_URL)
    schema.write_snapshot("nhlocal", "timeline.yml", raw, TIMELINE_URL)

    leads = parse_timeline(raw.decode("utf-8"))

    tables = schema.load_core()
    known_keys = {m["model_id"] for m in tables["models"]}
    known_keys |= {matchmod.normalize_name(r["identifier"])["key"]
                   for r in tables["crosswalk"] if r["namespace"] == "text_surface_forms"}

    queue = schema.STAGING_DIR / "review_queue.csv"
    existing = []
    if queue.exists():
        with queue.open(newline="", encoding="utf-8") as fh:
            existing = list(csv.DictReader(fh))
    seen = {(r["kind"], r["left_key"]) for r in existing}

    new_rows = []
    for lead in leads:
        key = matchmod.normalize_name(lead["name"])["key"]
        if not key or key in known_keys:
            continue
        row_key = f"{lead['name']}@{lead['date']}"
        if ("nhlocal_lead", row_key) in seen:
            continue
        seen.add(("nhlocal_lead", row_key))
        new_rows.append({
            "kind": "nhlocal_lead", "left_source": "nhlocal_aitimeline",
            "left_key": row_key, "right_source": "", "right_key": "",
            "score": "",
            "note": f"{lead['precision']}-precision community-timeline lead: "
                    f"{lead['context']}",
        })

    if new_rows:
        with queue.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=QUEUE_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(existing + new_rows)

    print(f"pull_nhlocal: {len(leads)} timeline mentions, "
          f"{len(new_rows)} new lead(s) queued for review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
