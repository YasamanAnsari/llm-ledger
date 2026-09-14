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
        "access_type": "api_only", "is_derivative": "false"}
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


def _model(model_id, org):
    return {c: "" for c in schema.MODELS.columns} | {
        "model_id": model_id, "developer_org_id": org, "model_type": "llm",
        "access_type": "api_only", "is_derivative": "false"}


def test_exact_id_in_crosswalk_wins_over_name_matching():
    # "o3" is too short to be its own id; the ledger calls it openai-o3 and
    # the crosswalk carries Azure's dated SKU. Name matching alone finds nothing.
    t = _tables()
    t["models"].append(_model("openai-o3", "openai"))
    t["crosswalk"] = [{"model_id": "openai-o3", "namespace": "openai_api", "identifier": "o3-2025-04-16"}]
    rows = {"azure_lifecycle": [_row("azure_lifecycle", "o3-2025-04-16", "azure", "2026-11-19")]}
    outcomes = load(rows, t, TODAY, NOW)
    assert outcomes["added"] == 1 and not any(k.startswith("unresolved") for k in outcomes)
    (e,) = t["events"]
    assert (e["model_id"], e["platform"], e["date"], e["detail"]) == ("openai-o3", "azure", "2026-11-19", "")


def test_partner_prefix_is_stripped_and_recorded_in_detail_not_platform():
    t = _tables()
    t["models"].append(_model("deepseek-v3-1", "deepseek"))
    rows = {"azure_lifecycle": [_row("azure_lifecycle", "FW-DeepSeek-V3.1", "azure", "2026-10-30")]}
    load(rows, t, TODAY, NOW)
    (e,) = t["events"]
    assert (e["model_id"], e["platform"], e["detail"]) == ("deepseek-v3-1", "azure", "served_by=Fireworks AI (FW-DeepSeek-V3.1)")
    # Re-running with the same rows changes nothing.
    stamp = t["models"][1]["record_updated"]
    assert load(rows, t, TODAY, "2026-10-02T00:00:00+00:00")["unchanged"] == 1
    assert t["models"][1]["record_updated"] == stamp


def test_crosswalk_and_name_disagreeing_goes_to_review_not_to_a_model():
    import lifecycle
    t = _tables()
    t["models"] += [_model("gpt-4o-mini", "openai"), _model("some-other", "openai")]
    t["crosswalk"] = [{"model_id": "some-other", "namespace": "openai_api", "identifier": "gpt-4o-mini-2024-07-18"}]
    rows = {"azure_lifecycle": [_row("azure_lifecycle", "gpt-4o-mini-2024-07-18", "azure", "2026-12-01")]}
    lifecycle.pending_review.clear()
    outcomes = load(rows, t, TODAY, NOW)
    assert outcomes["ambiguous:azure_lifecycle"] == 1 and not t["events"]
    (q,) = lifecycle.pending_review
    assert (q["kind"], q["left_key"], q["right_key"]) == (
        "lifecycle_ambiguous", "gpt-4o-mini-2024-07-18", "crosswalk:some-other|name:gpt-4o-mini")


def test_id_shared_by_a_model_and_its_snapshot_resolves_by_name():
    t = _tables()
    t["models"].append(_model("gpt-4o-2024-05-13", "openai") | {"snapshot_of": "gpt-4o"})
    t["crosswalk"] = [{"model_id": m, "namespace": "openai_api", "identifier": "gpt-4o-2024-05-13"}
                      for m in ("gpt-4o", "gpt-4o-2024-05-13")]
    rows = {"azure_lifecycle": [_row("azure_lifecycle", "gpt-4o-2024-05-13", "azure", "2026-03-31")]}
    outcomes = load(rows, t, TODAY, NOW)
    assert outcomes["added"] == 1 and t["events"][0]["model_id"] == "gpt-4o"
