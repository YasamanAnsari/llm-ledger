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
- Mistral:   `created` is stamped with the response time on every model
             (observed 2026-09-10: identical to the fetch second) and is
             dropped; `deprecation` (ISO datetime or null) is the published
             retirement; `aliases` lists the other ids that serve the same
             model and is kept so reconcile can flag split rows.

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
                      "max_input_tokens", "max_output_tokens", "aliases"]


def _unix_date(value) -> str:
    return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat() if value else ""


def _row(id: str, created_date: str = "", shutdown_date: str = "", display_name: str = "",
         max_input_tokens="", max_output_tokens="", aliases: list | None = None) -> dict:
    return {"id": id, "created_date": created_date, "shutdown_date": shutdown_date,
            "display_name": display_name, "max_input_tokens": max_input_tokens,
            "max_output_tokens": max_output_tokens, "aliases": "|".join(aliases or [])}


def _list(payload: dict, key: str, vendor: str) -> list:
    data = payload.get(key)
    if not isinstance(data, list) or not data:
        raise ValueError(f"{vendor} payload has no '{key}' list; schema changed?")
    return data


def normalize_openai(payload: dict) -> list:
    return [_row(m["id"], created_date=_unix_date(m.get("created")),
                 shutdown_date=m.get("shutdown_date") or "")
            for m in _list(payload, "data", "OpenAI")]


def normalize_anthropic(payload: dict) -> list:
    return [_row(m["id"], created_date=(m.get("created_at") or "")[:10],
                 display_name=m.get("display_name", ""),
                 max_input_tokens=m.get("max_input_tokens", ""),
                 max_output_tokens=m.get("max_tokens", ""))
            for m in _list(payload, "data", "Anthropic")]


def normalize_google(payload: dict) -> list:
    return [_row(m["name"].removeprefix("models/"), display_name=m.get("displayName", ""),
                 max_input_tokens=m.get("inputTokenLimit", ""),
                 max_output_tokens=m.get("outputTokenLimit", ""))
            for m in _list(payload, "models", "Gemini")]


def normalize_mistral(payload: dict) -> list:
    # `created` is the response time, not a date: never a claim.
    return [_row(m["id"], shutdown_date=(m.get("deprecation") or "")[:10],
                 display_name=m.get("name", ""),
                 max_input_tokens=m.get("max_context_length", ""),
                 aliases=m.get("aliases") or [])
            for m in _list(payload, "data", "Mistral")]


NORMALIZERS = {
    "openai_api": normalize_openai,
    "anthropic_api": normalize_anthropic,
    "google_api": normalize_google,
    "mistral_api": normalize_mistral,
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
        rows = sorted(NORMALIZERS[source](json.loads(payload)), key=lambda r: r["id"])
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
