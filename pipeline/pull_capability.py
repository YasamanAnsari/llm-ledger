"""Pull the Epoch Capabilities Index scores (CC BY 4.0) for the capability join.

ECI scores are never copied into core tables (validation rule 10); this
snapshot feeds only data/generated/llm_ledger_capability.csv, which
build.py joins through the crosswalk. Artificial Analysis is not pulled:
its Terms of Use allow personal, noncommercial use of the site only and
forbid redistributing any part of it.
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch
import schema

URL = "https://epoch.ai/data/eci_scores.csv"
SOURCE, FILENAME = "epoch_eci", "eci_scores.csv"
REQUIRED_COLUMNS = ("Model", "eci", "eci_ci_low", "eci_ci_high", "date", "Accessibility group")


def check(payload: bytes) -> int:
    """Rows in the payload; raises when a column the join reads is gone."""
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8")))
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"ECI CSV lacks {missing}; header is {reader.fieldnames}")
    return sum(1 for _ in reader)


def main() -> int:
    payload = fetch.get_bytes(URL)
    rows = check(payload)
    schema.write_snapshot(SOURCE, FILENAME, payload, URL)
    print(f"pull_capability: {rows} ECI rows -> {schema.snapshot_dir(SOURCE) / FILENAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
