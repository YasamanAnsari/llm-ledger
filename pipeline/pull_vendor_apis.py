"""Pull vendor model-list APIs that require credentials.

Each puller activates only when its environment variable is present and
skips with a clear message otherwise - no credentials are ever stored in the
repository, and no data is fabricated when a source is unavailable.
"""

from __future__ import annotations

import os
import sys
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


def main() -> int:
    pulled = 0
    for source, env_var, url, headers in VENDORS:
        key = os.environ.get(env_var, "")
        if not key:
            print(f"pull_vendor_apis: SKIP {source} ({env_var} not set)")
            continue
        payload = fetch.get_bytes(url, headers=headers(key))
        schema.write_snapshot(source, "models.json", payload, url)
        print(f"pull_vendor_apis: pulled {source} ({len(payload)} bytes)")
        pulled += 1
    print(f"pull_vendor_apis: {pulled}/{len(VENDORS)} vendor APIs pulled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
