"""Derived-field logic tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from build import LATEST_COLUMNS, build_reschedule_rows, compute_derived, latest_first
from confidence import curated_model_ids
from schema import MODELS, family_and_role


def _model(model_id="m1"):
    return {"model_id": model_id}


def _event(model_id, event_type, date, precision="day", region="global", confidence="inferred"):
    return {
        "model_id": model_id, "event_type": event_type, "date": date,
        "precision": precision, "region": region, "confidence": confidence,
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


def test_curated_models_are_those_with_a_verified_primary_page_event():
    curated = _event("m1", "api_ga", "2025-08-07") | {"confidence": "verified", "source_type": "vendor_blog"}
    inferred_page = _event("m2", "api_ga", "2025-08-07") | {"confidence": "inferred", "source_type": "vendor_blog"}
    machine = _event("m3", "api_ga", "2025-08-07") | {"confidence": "verified", "source_type": "api_metadata"}
    assert curated_model_ids([curated, inferred_page, machine]) == {"m1"}


def test_family_role_recomputed_unless_curated():
    curated = {"model_id": "m1", "canonical_name": "GPT-5.1", "family": "GPT-5", "variant_role": "base"}
    stale = {"model_id": "m2", "canonical_name": "Qwen2.5-72B-Instruct", "family": "old", "variant_role": "other"}
    reviewed = [_event("m1", "api_ga", "2025-08-07") | {"confidence": "verified", "source_type": "vendor_blog", "verified_by": "llm-ledger"}]
    a, b = compute_derived([curated, stale], reviewed)
    assert (a["family"], a["variant_role"]) == ("GPT-5", "base")        # curated stands
    assert (b["family"], b["variant_role"]) == ("Qwen2.5", "instruct")  # machine row re-derived


def test_derived_family_adopts_the_common_spelling():
    rows = [{"model_id": f"q{i}", "canonical_name": n, "family": "", "variant_role": ""}
            for i, n in enumerate(["Qwen3-8B", "Qwen3-32B", "qwen3-coder", "Nameless 7B"])]
    out = compute_derived(rows, [])
    assert [r["family"] for r in out] == ["Qwen3", "Qwen3", "Qwen3", "Nameless"]


def test_year_placeholder_never_sets_the_headline_date():
    events = [_event("m1", "api_ga", "2024-01-01", precision="year")]
    (row,) = compute_derived([_model()], events)
    assert row["first_public_availability_date"] == ""
    assert row["first_availability_via"] == ""
    assert row["first_availability_confidence"] == ""


def test_headline_confidence_follows_the_winning_event():
    events = [_event("m1", "api_ga", "2025-03-01", confidence="verified"),
              _event("m1", "weights_released", "2025-04-01", confidence="inferred")]
    (row,) = compute_derived([_model()], events)
    assert row["first_availability_confidence"] == "verified"
    assert LATEST_COLUMNS.index("first_availability_confidence") == 2


def test_readme_stats_block_is_replaced_in_place():
    from build import README_STATS_END, README_STATS_START, render_readme
    text = f"before\n{README_STATS_START}\nold\n{README_STATS_END}\nafter\n"
    out = render_readme(text, "new stats")
    assert out == f"before\n{README_STATS_START}\nnew stats\n{README_STATS_END}\nafter\n"


def test_machine_row_with_weights_event_becomes_open_weights():
    machine = {"model_id": "m1", "access_type": "api_only", "canonical_name": "M1"}
    curated = {"model_id": "m2", "access_type": "api_only", "canonical_name": "M2"}
    events = [_event("m1", "weights_released", "2025-01-01"),
              _event("m2", "weights_released", "2025-01-01"),
              _event("m2", "announced", "2025-01-01", confidence="verified") | {"source_type": "vendor_blog", "verified_by": "llm-ledger"}]
    a, b = compute_derived([machine, curated], events)
    assert a["access_type"] == "open_weights"
    assert b["access_type"] == "api_only"          # curated rows are a human call


def test_reschedules_chain_each_superseded_claim_to_the_next_statement():
    azure = "https://learn.microsoft.com/azure/retirements"
    events = [{"event_id": "o3-retired-2", "model_id": "o3", "event_type": "retired", "platform": "azure"}]

    def claim(day, superseded_on="", url=azure):
        return {"event_id": "o3-retired-2", "source_url": url, "date": day, "label": "azure_lifecycle (o3)",
                "first_party": "true", "superseded_on": superseded_on}
    claims = [claim("2026-10-01", "2026-09-05"), claim("2026-12-17", "2026-09-12"), claim("2026-11-19"),
              claim("2026-10-01", url="https://raw.githubusercontent.com/x/litellm.json")]
    rows = build_reschedule_rows(events, claims)
    assert [(r["from_date"], r["to_date"], r["days_moved"], r["observed_on"]) for r in rows] == [
        ("2026-10-01", "2026-12-17", "77", "2026-09-05"),
        ("2026-12-17", "2026-11-19", "-28", "2026-09-12"),
    ]
    assert rows[0]["source"] == "azure_lifecycle" and rows[0]["platform"] == "azure"
