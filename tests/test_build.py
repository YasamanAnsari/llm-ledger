"""Derived-field logic tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from build import LATEST_COLUMNS, compute_derived, latest_first
from schema import MODELS, family_and_role


def _model(model_id="m1"):
    return {"model_id": model_id}


def _event(model_id, event_type, date, precision="day", region="global"):
    return {
        "model_id": model_id, "event_type": event_type, "date": date,
        "precision": precision, "region": region,
    }


def test_min_availability_wins():
    events = [
        _event("m1", "api_ga", "2025-03-01"),
        _event("m1", "weights_released", "2025-04-01"),
    ]
    (row,) = compute_derived([_model()], events)
    assert row["first_public_availability_date"] == "2025-03-01"
    assert row["first_availability_via"] == "api_ga"


def test_tie_priority_weights_over_api():
    events = [
        _event("m1", "api_ga", "2025-03-01"),
        _event("m1", "weights_released", "2025-03-01"),
        _event("m1", "consumer_rollout", "2025-03-01"),
    ]
    (row,) = compute_derived([_model()], events)
    assert row["first_availability_via"] == "weights_released"


def test_fallback_suffix():
    events = [_event("m1", "api_preview", "2025-02-01")]
    (row,) = compute_derived([_model()], events)
    assert row["first_public_availability_date"] == "2025-02-01"
    assert row["first_availability_via"] == "api_preview_fallback"


def test_non_global_region_ignored():
    events = [
        _event("m1", "api_ga", "2025-01-01", region="CN"),
        _event("m1", "api_ga", "2025-06-01"),
    ]
    (row,) = compute_derived([_model()], events)
    assert row["first_public_availability_date"] == "2025-06-01"


def test_anticipation_days():
    events = [
        _event("m1", "announced", "2025-01-10"),
        _event("m1", "api_ga", "2025-01-31"),
    ]
    (row,) = compute_derived([_model()], events)
    assert row["anticipation_days"] == "21"


def test_anticipation_null_when_precision_coarse():
    events = [
        _event("m1", "announced", "2025-01-01", precision="quarter"),
        _event("m1", "api_ga", "2025-01-31"),
    ]
    (row,) = compute_derived([_model()], events)
    assert row["anticipation_days"] == ""


def test_no_availability_leaves_fields_empty():
    events = [_event("m1", "announced", "2025-01-10")]
    (row,) = compute_derived([_model()], events)
    assert row["first_public_availability_date"] == ""
    assert row["first_availability_via"] == ""
    assert row["anticipation_days"] == ""


def test_latest_first_newest_top_undated_last_id_tiebreak():
    def row(model_id, date):
        return {"model_id": model_id, "first_public_availability_date": date}

    models = [row("b", "2025-03-01"), row("undated", ""), row("c", "2025-01-01"),
              row("a", "2025-03-01")]
    assert [r["model_id"] for r in latest_first(models)] == ["a", "b", "c", "undated"]
    assert LATEST_COLUMNS[0] == "first_public_availability_date"
    assert set(LATEST_COLUMNS) <= set(MODELS.columns) and len(set(LATEST_COLUMNS)) == len(LATEST_COLUMNS)


def test_family_and_role_from_name():
    cases = {
        "Qwen2.5-72B-Instruct": ("Qwen2.5", "instruct"),
        "Llama 3.1 405B Instruct": ("Llama 3.1", "instruct"),
        "o3-mini": ("o3", "mini"),
        "Claude 3.5 Sonnet": ("Claude 3.5", ""),
        "Gemini 1.5 Flash": ("Gemini 1.5", "mini"),
        "DeepSeek-V3": ("DeepSeek-V3", ""),
        "Mixtral 8x7B Instruct": ("Mixtral", "instruct"),
        "Qwen3 235B-A22B": ("Qwen3", ""),
        "GPT-4o (2024-05-13 snapshot)": ("GPT-4o", ""),
        "Phi-3-mini-128k-instruct": ("Phi-3", "instruct"),
        "gemma-3-1b-it": ("gemma-3", "instruct"),
        "Command R+": ("Command R", ""),
        "Kimi K2 Thinking": ("Kimi K2", "thinking"),
    }
    for name, expected in cases.items():
        assert family_and_role(name) == expected, (name, family_and_role(name))


def test_review_status_distinguishes_people_from_the_project():
    person = [_event("m1", "api_ga", "2025-08-07") | {"confidence": "verified", "source_type": "vendor_blog", "verified_by": "Yasaman Ansari"}]
    project = [_event("m2", "api_ga", "2025-08-07") | {"confidence": "verified", "source_type": "vendor_blog", "verified_by": "llm-ledger"}]
    agent = [_event("m3", "api_ga", "2025-08-07") | {"confidence": "verified", "source_type": "vendor_blog", "verified_by": "llm-ledger-agent"}]
    machine = [_event("m4", "api_ga", "2025-08-07") | {"confidence": "verified", "source_type": "api_metadata", "verified_by": "llm-ledger"}]
    rows = compute_derived([_model("m1"), _model("m2"), _model("m3"), _model("m4"), _model("m5")],
                           person + project + agent + machine)
    assert [r["review_status"] for r in rows] == [
        "human_reviewed", "curated", "curated", "machine_corroborated", "unreviewed"]


def test_family_role_recomputed_unless_curated():
    curated = {"model_id": "m1", "canonical_name": "GPT-5.1", "family": "GPT-5", "variant_role": "base"}
    stale = {"model_id": "m2", "canonical_name": "Qwen2.5-72B-Instruct", "family": "old", "variant_role": "other"}
    reviewed = [_event("m1", "api_ga", "2025-08-07") | {"confidence": "verified", "source_type": "vendor_blog", "verified_by": "llm-ledger"}]
    a, b = compute_derived([curated, stale], reviewed)
    assert a["review_status"] == "curated"
    assert (a["family"], a["variant_role"]) == ("GPT-5", "base")        # curated stands
    assert (b["family"], b["variant_role"]) == ("Qwen2.5", "instruct")  # machine row re-derived


def test_derived_family_adopts_the_common_spelling():
    rows = [{"model_id": f"q{i}", "canonical_name": n, "family": "", "variant_role": ""}
            for i, n in enumerate(["Qwen3-8B", "Qwen3-32B", "qwen3-coder", "Nameless 7B"])]
    out = compute_derived(rows, [])
    assert [r["family"] for r in out] == ["Qwen3", "Qwen3", "Qwen3", "Nameless"]
