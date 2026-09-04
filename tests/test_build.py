"""Derived-field logic tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from build import LATEST_COLUMNS, compute_derived, latest_first
from schema import MODELS


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
    assert sorted(LATEST_COLUMNS) == sorted(MODELS.columns)
