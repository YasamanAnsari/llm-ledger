"""observe: daily listings fold into runs; ids resolve through the crosswalk."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import observe
import schema

PRICE = schema.PRICE_OBSERVATIONS


def _price(price_input: str) -> dict:
    return {"source": "openrouter", "provider": "openrouter", "api_id": "acme/acme-1",
            "price_input": price_input, "price_output": "0.00001", "price_cached": "",
            "currency": "USD", "unit": "per_token", "source_url": "https://openrouter.ai/api/v1/models"}


def test_a_run_grows_while_values_hold_and_breaks_on_a_change_or_a_missed_day() -> None:
    rows: list = []
    assert observe.extend_runs(rows, [_price("0.000002")], PRICE, date(2026, 10, 1)) == 1
    assert observe.extend_runs(rows, [_price("0.000002")], PRICE, date(2026, 10, 2)) == 0
    assert observe.extend_runs(rows, [_price("0.000001")], PRICE, date(2026, 10, 3)) == 1
    # No pull on 10-04: the same price on 10-05 is a new run, not a continuation.
    assert observe.extend_runs(rows, [_price("0.000001")], PRICE, date(2026, 10, 5)) == 1
    assert [(r["price_input"], r["first_observed"], r["last_observed"]) for r in rows] == [
        ("0.000002", "2026-10-01", "2026-10-02"),
        ("0.000001", "2026-10-03", "2026-10-03"),
        ("0.000001", "2026-10-05", "2026-10-05")]
    try:
        observe.extend_runs(rows, [_price("0.1"), _price("0.2")], PRICE, date(2026, 10, 6))
    except ValueError:
        pass
    else:
        raise AssertionError("one id at two prices on one day must fail")


def test_resolver_prefers_the_exact_identifier_and_refuses_an_ambiguous_key() -> None:
    crosswalk = [
        {"model_id": "acme-1", "namespace": "models_dev", "identifier": "acme/acme-1"},
        {"model_id": "acme-1-0901", "namespace": "openrouter", "identifier": "acme/acme-1-0901"},
        {"model_id": "acme-2", "namespace": "models_dev", "identifier": "acme/acme-2"},
        {"model_id": "acme-2-pro", "namespace": "openrouter", "identifier": "acme/acme-2"},
    ]
    resolve = observe.model_resolver(crosswalk)
    assert resolve("models_dev", "acme", "acme-1") == "acme-1"
    assert resolve("models_dev", "reseller", "acme/acme-1") == "acme-1"      # key fallback
    assert resolve("models_dev", "reseller", "acme-1-0901") == "acme-1-0901"  # snapshot kept apart
    assert resolve("openrouter", "openrouter", "acme/acme-2") == "acme-2-pro"
    assert resolve("models_dev", "reseller", "acme-2") == ""                  # two models share the key


def test_market_prices_convert_to_per_million_and_drop_the_router_marker() -> None:
    import market
    assert market.per_1m("2.5e-06", "per_token") == "2.5"
    assert market.per_1m("0.00001", "per_token") == "10"
    assert market.per_1m("0.3", "per_1m_tokens") == "0.3"
    assert market.per_1m("-1", "per_token") == ""
    assert market.per_1m("", "per_token") == ""
