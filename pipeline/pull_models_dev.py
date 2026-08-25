"""Pull the models.dev catalog and store a raw snapshot plus a normalized CSV.

models.dev serves a single JSON document keyed by provider, each provider
carrying a `models` mapping. We keep the raw payload verbatim (gitignored;
manifest committed) and normalize the fields the ledger uses.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch
import schema

URL = "https://models.dev/api.json"

NORMALIZED_COLUMNS = [
    "provider", "model_key", "name", "release_date", "last_updated",
    "knowledge_cutoff", "open_weights", "reasoning", "tool_call",
    "context_length", "max_output_tokens", "cost_input", "cost_output",
    "cost_cache_read", "modalities_in", "modalities_out",
]


def normalize(payload: dict) -> list:
    if not isinstance(payload, dict) or not payload:
        raise ValueError("models.dev payload is not a non-empty JSON object")
    rows = []
    for provider_id, provider in sorted(payload.items()):
        models = provider.get("models") if isinstance(provider, dict) else None
        if not isinstance(models, dict):
            continue
        for model_key, m in sorted(models.items()):
            if not isinstance(m, dict):
                continue
            cost = m.get("cost") or {}
            limit = m.get("limit") or {}
            modalities = m.get("modalities") or {}
            rows.append({
                "provider": provider_id,
                "model_key": model_key,
                "name": m.get("name", ""),
                "release_date": m.get("release_date", ""),
                "last_updated": m.get("last_updated", ""),
                "knowledge_cutoff": m.get("knowledge", ""),
                "open_weights": str(m.get("open_weights", "")).lower(),
                "reasoning": str(m.get("reasoning", "")).lower(),
                "tool_call": str(m.get("tool_call", "")).lower(),
                "context_length": limit.get("context", ""),
                "max_output_tokens": limit.get("output", ""),
                "cost_input": cost.get("input", ""),
                "cost_output": cost.get("output", ""),
                "cost_cache_read": cost.get("cache_read", ""),
                "modalities_in": "|".join(modalities.get("input", []) or []),
                "modalities_out": "|".join(modalities.get("output", []) or []),
            })
    if not rows:
        raise ValueError("models.dev normalization produced zero rows; schema changed?")
    return rows


def main() -> int:
    payload_bytes = fetch.get_bytes(URL)
    schema.write_snapshot("models_dev", "api.json", payload_bytes, URL)
    rows = normalize(json.loads(payload_bytes))

    out = schema.snapshot_dir("models_dev") / "normalized.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=NORMALIZED_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"pull_models_dev: {len(rows)} models -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
