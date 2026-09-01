"""Pull vendor model-list APIs that require credentials.

Each puller activates only when its environment variable is present and
skips with a clear message otherwise - no credentials are ever stored in the
repository, and no data is fabricated when a source is unavailable.

The raw payload is snapshotted verbatim; a normalized.csv is written for the
vendors whose response shape is known:

- OpenAI:    `created` (unix) is when the model object was registered;
             `shutdown_date` (YYYY-MM-DD or null) the published retirement.
- Anthropic: `created_at` (ISO) is the registry timestamp.
- Google:    no dates in the listing; ids and token limits only.
- Mistral:   raw snapshot only until a key is available to confirm the shape.

Registry timestamps precede the public launch by days (observed 1-16d), so
reconcile.py treats them as corroborating claims, not first-party dates.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch
import schema

VENDORS = (
    # (source name, env var, url, extra headers builder)
    ("openai_api", "OPENAI_API_KEY", "https://api.openai.com/v1/models",
     lambda key: {"Authorization": f"Bearer {key}"}),
    ("anthropic_api", "ANTHROPIC_API_KEY", "https://api.anthropic.com/v1/models",
     lambda key: {"x-api-key": key, "anthropic-version": "2023-06-01"}),
    ("google_api", "GEMINI_API_KEY",
     "https://generativelanguage.googleapis.com/v1beta/models",
     lambda key: {"x-goog-api-key": key}),
    ("mistral_api", "MISTRAL_API_KEY", "https://api.mistral.ai/v1/models",
     lambda key: {"Authorization": f"Bearer {key}"}),
)

NORMALIZED_COLUMNS = ["id", "created_date", "shutdown_date", "display_name",
                      "max_input_tokens", "max_output_tokens"]


def _unix_date(value) -> str:
    return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat() if value else ""


def normalize_openai(payload: dict) -> list:
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("OpenAI payload has no 'data' list; schema changed?")
    return [{
        "id": m["id"],
        "created_date": _unix_date(m.get("created")),
        "shutdown_date": m.get("shutdown_date") or "",
        "display_name": "",
        "max_input_tokens": "",
        "max_output_tokens": "",
    } for m in data]


def normalize_anthropic(payload: dict) -> list:
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("Anthropic payload has no 'data' list; schema changed?")
    return [{
        "id": m["id"],
        "created_date": (m.get("created_at") or "")[:10],
        "shutdown_date": "",
        "display_name": m.get("display_name", ""),
        "max_input_tokens": m.get("max_input_tokens", ""),
        "max_output_tokens": m.get("max_tokens", ""),
    } for m in data]


def normalize_google(payload: dict) -> list:
    models = payload.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("Gemini payload has no 'models' list; schema changed?")
    return [{
        "id": m["name"].removeprefix("models/"),
        "created_date": "",
        "shutdown_date": "",
        "display_name": m.get("displayName", ""),
        "max_input_tokens": m.get("inputTokenLimit", ""),
        "max_output_tokens": m.get("outputTokenLimit", ""),
    } for m in models]


NORMALIZERS = {
    "openai_api": normalize_openai,
    "anthropic_api": normalize_anthropic,
    "google_api": normalize_google,
}


def main() -> int:
    pulled = 0
    for source, env_var, url, headers in VENDORS:
        key = os.environ.get(env_var, "")
        if not key:
            print(f"pull_vendor_apis: SKIP {source} ({env_var} not set)")
            continue
        payload = fetch.get_bytes(url, headers=headers(key))
        schema.write_snapshot(source, "models.json", payload, url)
        pulled += 1
        normalize = NORMALIZERS.get(source)
        if normalize is None:
            print(f"pull_vendor_apis: pulled {source} (raw only; shape not yet normalized)")
            continue
        rows = sorted(normalize(json.loads(payload)), key=lambda r: r["id"])
        out = schema.snapshot_dir(source) / "normalized.csv"
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=NORMALIZED_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        print(f"pull_vendor_apis: pulled {source}: {len(rows)} models -> {out}")
    print(f"pull_vendor_apis: {pulled}/{len(VENDORS)} vendor APIs pulled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
