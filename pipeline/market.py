"""The market on a date: which ledger models each provider listed on one
day, at what price and with what limits, with the observation behind it.

Usage:
    python pipeline/market.py --date 2026-10-15          # CSV to stdout
    python pipeline/market.py --date 2026-10-15 --out f.csv

`data/generated/market_on_date.csv` is this view for the newest observed
day (build.py writes it). Rows come from availability runs that cover the
day and name a ledger model; price and capability come from the same
source's runs for the same id on that day. Prices are converted to USD per
1M tokens from the source's unit; nothing else is changed.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import schema

MARKET_COLUMNS = (
    "date", "model_id", "canonical_name", "developer_org_id", "access_type",
    "license_family", "provider", "source", "api_id",
    "price_input_usd_per_1m", "price_output_usd_per_1m", "price_cached_usd_per_1m",
    "context_length", "max_output", "modalities_in", "modalities_out",
    "tool_use", "structured_output", "reasoning", "observed_from", "source_url",
)
PER_1M = {"per_1m_tokens": Decimal(1), "per_token": Decimal(1_000_000)}


def per_1m(value: str, unit: str) -> str:
    """A stated price in USD per 1M tokens. Blank stays blank; a negative
    value is OpenRouter's marker for variable router pricing, not a price."""
    if not value:
        return ""
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"price {value!r} is not a number") from exc
    if amount < 0:
        return ""
    return format((amount * PER_1M[unit]).normalize(), "f")


def _covering(rows: list, day: str) -> dict:
    """(source, provider, api_id) -> the run covering `day`."""
    return {(r["source"], r["provider"], r["api_id"]): r for r in rows
            if r["first_observed"] <= day <= r["last_observed"]}


def market_rows(day: str, models: list, observations: dict) -> list:
    """Rows of the market view for one ISO day."""
    by_model = {m["model_id"]: m for m in models}
    prices = _covering(observations[schema.PRICE_OBSERVATIONS.name], day)
    limits = _covering(observations[schema.CAPABILITY_OBSERVATIONS.name], day)
    rows = []
    for subject, run in _covering(observations[schema.AVAILABILITY_OBSERVATIONS.name], day).items():
        model = by_model.get(run["model_id"])
        if model is None:
            continue
        price = prices.get(subject, {})
        cap = limits.get(subject, {})
        unit = price.get("unit", "per_1m_tokens")
        rows.append({
            "date": day, "model_id": model["model_id"], "canonical_name": model["canonical_name"],
            "developer_org_id": model["developer_org_id"], "access_type": model["access_type"],
            "license_family": model["license_family"], "provider": run["provider"],
            "source": run["source"], "api_id": run["api_id"],
            "price_input_usd_per_1m": per_1m(price.get("price_input", ""), unit),
            "price_output_usd_per_1m": per_1m(price.get("price_output", ""), unit),
            "price_cached_usd_per_1m": per_1m(price.get("price_cached", ""), unit),
            **{c: cap.get(c, "") for c in ("context_length", "max_output", "modalities_in",
                                           "modalities_out", "tool_use", "structured_output",
                                           "reasoning")},
            "observed_from": run["first_observed"], "source_url": run["source_url"],
        })
    return sorted(rows, key=lambda r: (r["model_id"], r["source"], r["provider"], r["api_id"]))


def latest_observed_day(observations: dict) -> str:
    days = [r["last_observed"] for r in observations[schema.AVAILABILITY_OBSERVATIONS.name]]
    if not days:
        raise FileNotFoundError("no availability observations under data/observations")
    return max(days)


def load_observations() -> dict:
    return {t.name: schema.read_table(t, schema.OBSERVATIONS_DIR) for t in schema.OBSERVATION_TABLES}


def market_bytes(day: str, models: list, observations: dict) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=MARKET_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(market_rows(day, models, observations))
    return buf.getvalue().encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", required=True, type=date.fromisoformat,
                        help="ISO day to reconstruct")
    parser.add_argument("--out", type=Path, help="write here instead of stdout")
    args = parser.parse_args()
    observations = load_observations()
    day = args.date.isoformat()
    first = min(r["first_observed"] for r in observations[schema.AVAILABILITY_OBSERVATIONS.name])
    if not first <= day <= latest_observed_day(observations):
        raise SystemExit(f"market: {day} is outside the observed span {first}..{latest_observed_day(observations)}")
    payload = market_bytes(day, schema.read_table(schema.MODELS), observations)
    if args.out:
        args.out.write_bytes(payload)
    else:
        sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
