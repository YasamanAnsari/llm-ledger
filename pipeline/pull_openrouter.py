"""Pull the OpenRouter model list and store a raw snapshot plus normalized CSV.

OpenRouter's `created` field is the unix timestamp at which the model was
listed on OpenRouter - a lower bound on availability, used as an `inferred`
fallback signal per the field-to-source map.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch
import schema

URL = "https://openrouter.ai/api/v1/models"

NORMALIZED_COLUMNS = [
    "id", "canonical_slug", "name", "created_date", "context_length",
    "price_prompt", "price_completion", "modalities_in", "modalities_out",
    "hugging_face_id", "expiration_date",
]


def _created_date(created) -> str:
    if not created:
        return ""
    return datetime.fromtimestamp(int(created), tz=timezone.utc).date().isoformat()


def _expiration(m: dict) -> str:
    """Any deprecation/expiration hint OpenRouter exposes, else empty."""
    for key, value in m.items():
        if value and ("expir" in key.lower() or "deprecat" in key.lower()):
            return str(value)
    return ""


def normalize(payload: dict) -> list:
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("OpenRouter payload has no 'data' list; schema changed?")
    rows = []
    for m in data:
        architecture = m.get("architecture") or {}
        pricing = m.get("pricing") or {}
        rows.append({
            "id": m.get("id", ""),
            "canonical_slug": m.get("canonical_slug", ""),
            "name": m.get("name", ""),
            "created_date": _created_date(m.get("created")),
            "context_length": m.get("context_length", ""),
            "price_prompt": pricing.get("prompt", ""),
            "price_completion": pricing.get("completion", ""),
            "modalities_in": "|".join(architecture.get("input_modalities", []) or []),
            "modalities_out": "|".join(architecture.get("output_modalities", []) or []),
            "hugging_face_id": m.get("hugging_face_id", "") or "",
            "expiration_date": _expiration(m),
        })
    rows.sort(key=lambda r: r["id"])
    return rows


def main() -> int:
    payload_bytes = fetch.get_bytes(URL)
    schema.write_snapshot("openrouter", "models.json", payload_bytes, URL)
    rows = normalize(json.loads(payload_bytes))

    out = schema.snapshot_dir("openrouter") / "normalized.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=NORMALIZED_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"pull_openrouter: {len(rows)} models -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
