"""lifecycle.load: platform scoping and identity resolution."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import schema
from lifecycle import load

TODAY, NOW = date(2026, 10, 1), "2026-10-01T00:00:00+00:00"


def _tables():
    m = {c: "" for c in schema.MODELS.columns} | {
        "model_id": "gpt-4o", "developer_org_id": "openai", "model_type": "llm",
        "access_type": "api_only", "is_derivative": "false", "review_status": "unreviewed"}
    return {"organizations": [], "models": [m], "events": [], "claims": [],
            "crosswalk": [], "attributes": []}


def _row(source, model_ref, platform, retire):
    return {"source": source, "model_ref": model_ref, "platform": platform,
            "retire_date": retire, "detail": "", "url": f"https://example.com/{source}"}


def test_azure_schedule_is_first_party_on_azure_and_litellm_vendor_row_is_global():
    t = _tables()
    rows = {"azure_lifecycle": [_row("azure_lifecycle", "gpt-4o-2024-05-13", "azure", "2026-03-31")],
            "litellm": [_row("litellm", "gpt-4o", "openai", "2026-06-30"),
                        _row("litellm", "azure/gpt-4o", "azure", "2026-03-31"),
                        _row("litellm", "nonesuch-9", "openai", "2026-06-30")]}
    outcomes = load(rows, t, TODAY, NOW)
    by_platform = {e["platform"]: e for e in t["events"]}
    assert by_platform["azure"]["confidence"] == "verified"      # first-party + litellm agree
    assert by_platform[""]["confidence"] == "inferred"           # litellm alone, vendor scope
    assert all(e["platform"] in schema.PLATFORMS | {""} for e in t["events"])
    assert outcomes["added"] == 2 and outcomes["unresolved:litellm"] == 1
    assert t["models"][0]["record_updated"] == NOW
    assert len(t["claims"]) == 3
