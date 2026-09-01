"""reconcile_cluster: a matched cluster becomes typed claims, not guesses."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import reconcile
from match import MATCHED_COLUMNS

TODAY = date(2026, 9, 1)


def _cluster(**overrides) -> dict:
    row = {c: "" for c in MATCHED_COLUMNS}
    row.update({
        "match_key": "acme-1", "sources": "models_dev|openrouter",
        "or_prefix": "openai", "md_provider": "openai", "md_model_key": "acme-1",
        "md_release_date": "2025-01-15", "md_open_weights": "false",
        "md_modalities_in": "text", "md_modalities_out": "text",
        "or_id": "openai/acme-1", "or_created": "2025-01-16",
        "md_snapshot_date": "2026-09-01",
    })
    row.update(overrides)
    return row


def _events_by_type(draft: dict) -> dict:
    return {e["event_type"]: e for e in draft["events"]}


def test_closed_model_gets_api_ga_and_openrouter_platform_row() -> None:
    ev = _events_by_type(reconcile.reconcile_cluster(_cluster(), TODAY))
    assert set(ev) == {"api_ga", "platform_availability"}
    assert ev["api_ga"]["claims"][0].date == date(2025, 1, 15)
    assert ev["platform_availability"]["platform"] == "openrouter"
    assert ev["platform_availability"]["claims"][0].first_party


def test_open_weights_model_gets_weights_released_not_api_ga() -> None:
    ev = _events_by_type(reconcile.reconcile_cluster(_cluster(md_open_weights="true"), TODAY))
    assert "weights_released" in ev and "api_ga" not in ev


def test_jan_first_is_a_year_precision_claim() -> None:
    ev = _events_by_type(reconcile.reconcile_cluster(_cluster(md_release_date="2024-01-01"), TODAY))
    assert ev["api_ga"]["claims"][0].precision == "year"


def test_epoch_publication_after_availability_is_not_an_announcement() -> None:
    ev = _events_by_type(reconcile.reconcile_cluster(
        _cluster(sources="models_dev|epoch", epoch_model="Acme 1",
                 epoch_publication_date="2025-02-01"), TODAY))
    assert "announced" not in ev
    ev = _events_by_type(reconcile.reconcile_cluster(
        _cluster(sources="models_dev|epoch", epoch_model="Acme 1",
                 epoch_publication_date="2025-01-10"), TODAY))
    assert ev["announced"]["claims"][0].date == date(2025, 1, 10)


def test_vendor_registry_is_a_bound_and_shutdown_is_first_party() -> None:
    vendor = {"acme-1": {
        "source": "openai_api", "org_id": "openai", "url": "https://api.openai.com/v1/models",
        "ids": ["acme-1", "acme-1-2025-01-13"], "created": ["2025-01-13", "2025-01-13"],
        "shutdown": ["2026-12-01", "2026-12-01"],
    }}
    draft = reconcile.reconcile_cluster(_cluster(), TODAY, vendor)
    ev = _events_by_type(draft)
    registry = [c for c in ev["api_ga"]["claims"] if "openai_api" in c.label]
    assert registry and registry[0].bound and not registry[0].first_party
    assert ev["retired"]["claims"][0].first_party
    assert ev["retired"]["claims"][0].date == date(2026, 12, 1)
    assert {x["namespace"] for x in draft["crosswalk"]} >= {"openai_api", "models_dev", "openrouter"}


def test_vendor_api_only_speaks_for_its_own_org() -> None:
    vendor = {"acme-1": {"source": "anthropic_api", "org_id": "anthropic",
                         "url": "https://api.anthropic.com/v1/models",
                         "ids": ["acme-1"], "created": ["2025-01-13"], "shutdown": [""]}}
    draft = reconcile.reconcile_cluster(_cluster(), TODAY, vendor)
    assert not any(x["namespace"] == "anthropic_api" for x in draft["crosswalk"])


def test_far_future_expiration_sentinel_is_ignored() -> None:
    ev = _events_by_type(reconcile.reconcile_cluster(_cluster(or_expiration="2099-01-01"), TODAY))
    assert "retired" not in ev


def test_single_source_or_unresolvable_org_yields_nothing() -> None:
    assert reconcile.reconcile_cluster(_cluster(sources="models_dev"), TODAY) is None
    assert reconcile.reconcile_cluster(
        _cluster(match_key="zzz", or_prefix="nobody", md_provider="nobody"), TODAY) is None


def test_attributes_come_from_models_dev_without_guessing_reasoning_type() -> None:
    draft = reconcile.reconcile_cluster(
        _cluster(md_reasoning="true", md_context_length="128000", md_cost_input="1.5"), TODAY)
    a = draft["attributes"]
    assert (a["reasoning_supported"], a["reasoning_type"]) == ("true", "")
    assert (a["context_length"], a["price_input"], a["price_date"]) == ("128000", "1.5", "2026-09-01")
    a = reconcile.reconcile_cluster(_cluster(md_reasoning="false"), TODAY)["attributes"]
    assert a["reasoning_type"] == "none"
