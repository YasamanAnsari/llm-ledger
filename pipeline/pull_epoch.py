"""Pull the Epoch AI models CSV (CC BY 4.0) for the enrichment artifact.

Epoch numbers are never copied into core tables (validation rule 10); this
snapshot feeds only data/generated/llm_ledger_enriched.csv and provides one
dating signal (publication date) for the disagreement report.
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch
import schema

URL = "https://epoch.ai/data/all_ai_models.csv"

NORMALIZED_COLUMNS = [
    "model", "organization", "publication_date", "confidence",
    "accessibility", "country", "link",
]

# Normalized column -> substrings to look for in Epoch's header.
HEADER_TOKENS = {
    "model": ("model", "system"),
    "organization": ("organization",),
    "publication_date": ("publication date",),
    "confidence": ("confidence",),
    "accessibility": ("accessibility",),
    "country": ("country",),
    "link": ("link",),
}


def _map_header(header: list) -> dict:
    mapping = {}
    for target, tokens in HEADER_TOKENS.items():
        for col in header:
            low = col.lower()
            if any(low == t or low.startswith(t) for t in tokens):
                mapping[target] = col
                break
    for required in ("model", "publication_date"):
        if required not in mapping:
            raise ValueError(
                f"Epoch CSV header lacks a recognizable '{required}' column: {header}"
            )
    return mapping


def normalize(payload: bytes) -> list:
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8")))
    header = list(reader.fieldnames or [])
    mapping = _map_header(header)
    rows = []
    for row in reader:
        model = (row.get(mapping["model"]) or "").strip()
        if not model:
            continue
        rows.append({
            target: (row.get(mapping[target]) or "").strip() if target in mapping else ""
            for target in NORMALIZED_COLUMNS
        } | {"model": model})
    if not rows:
        raise ValueError("Epoch normalization produced zero rows; schema changed?")
    rows.sort(key=lambda r: r["model"])
    return rows


def main() -> int:
    payload = fetch.get_bytes(URL)
    schema.write_snapshot("epoch", "all_ai_models.csv", payload, URL)
    rows = normalize(payload)

    out = schema.snapshot_dir("epoch") / "normalized.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=NORMALIZED_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"pull_epoch: {len(rows)} models -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
