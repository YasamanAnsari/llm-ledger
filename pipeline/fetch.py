"""Shared HTTP helper for Tier-1 pullers."""

from __future__ import annotations

import requests

USER_AGENT = "llm-ledger-pipeline/1.0 (research dataset builder)"
TIMEOUT_SECONDS = 60


def get_bytes(url: str, headers: dict | None = None) -> bytes:
    merged = {"User-Agent": USER_AGENT}
    if headers:
        merged.update(headers)
    response = requests.get(url, headers=merged, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.content
