"""OpenRouter's public daily token ranking, from its Data API.

`GET /api/v1/datasets/rankings-daily` returns, for each day since
2025-01-01, the 50 public models that processed the most tokens on
OpenRouter plus one `other` row for everything else. The dataset is CC BY
4.0; cite it as "Source: OpenRouter (openrouter.ai/rankings), as of
<as_of>. Licensed under CC BY 4.0." Every pull re-reads the whole span
(OpenRouter may revise past days) and rewrites
data/observations/usage_observations.csv from it; the payloads go under
data/raw/openrouter_rankings/<day>/ with their `meta` block.

Needs OPENROUTER_API_KEY; without it the puller skips. Spans are at most
366 days (the API's limit); the API allows 30 requests a minute.

Usage:
    python pipeline/pull_openrouter_rankings.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch
import observe
import schema

SOURCE = "openrouter_rankings"
ENDPOINT = "https://openrouter.ai/api/v1/datasets/rankings-daily"
FIRST_DAY = date(2025, 1, 1)
MAX_SPAN_DAYS = 366


def spans(first: date, last: date) -> list:
    """(start, end) pairs covering first..last, each at most MAX_SPAN_DAYS
    days inclusive."""
    out, start = [], first
    while start <= last:
        end = min(start + timedelta(days=MAX_SPAN_DAYS - 1), last)
        out.append((start, end))
        start = end + timedelta(days=1)
    return out


def permaslug_ids(listings: list) -> dict:
    """Permaslug -> OpenRouter model id, from model listings (each the
    `data` of a /api/v1/models payload). The ranking names a model by its
    dated `canonical_slug`; ':free', ':batch' and the like are variants of
    one id. A slug that two base ids claimed is left out."""
    found: dict = defaultdict(set)
    for listing in listings:
        for m in listing:
            if m.get("canonical_slug"):
                found[m["canonical_slug"]].add(m["id"].split(":")[0])
    return {slug: next(iter(ids)) for slug, ids in found.items() if len(ids) == 1}


def archived_listings() -> list:
    """Every OpenRouter /models payload kept under data/raw/openrouter."""
    return [json.loads(p.read_text(encoding="utf-8"))["data"]
            for p in sorted((schema.RAW_DIR / "openrouter").glob("*/models.json"))]


def usage_rows(payload: dict, url: str, resolve, slug_ids: dict) -> list:
    """Rows of usage_observations for one API response. Token counts stay
    the exact integers the API states (as strings); `rank` orders a day's
    named models by tokens, ties sharing the higher rank. A permaslug the
    listings do not know is looked up as an id itself."""
    by_day: dict = defaultdict(list)
    for r in payload["data"]:
        if not r["total_tokens"].isdigit():
            raise ValueError(f"{SOURCE}: {r['date']} {r['model_permaslug']} total_tokens "
                             f"{r['total_tokens']!r} is not a whole number")
        by_day[r["date"]].append(r)
    rows = []
    for day, entries in by_day.items():
        if sum(1 for r in entries if r["model_permaslug"] == schema.USAGE_OTHER) != 1:
            raise ValueError(f"{SOURCE}: {day} does not carry exactly one `other` row")
        total = sum(int(r["total_tokens"]) for r in entries)
        named = sorted((int(r["total_tokens"]) for r in entries
                        if r["model_permaslug"] != schema.USAGE_OTHER), reverse=True)
        for r in entries:
            slug, tokens = r["model_permaslug"], int(r["total_tokens"])
            other = slug == schema.USAGE_OTHER
            base = slug.split(":")[0]
            rows.append({
                "date": day, "model_permaslug": slug,
                "model_id": "" if other else resolve("openrouter", "openrouter",
                                                     slug_ids.get(base, base)),
                "total_tokens": r["total_tokens"],
                "rank": "" if other else str(named.index(tokens) + 1),
                "day_total_tokens": str(total), "as_of": payload["meta"]["as_of"],
                "source_url": url})
    return rows


def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        print(f"{SOURCE}: OPENROUTER_API_KEY not set; skipped")
        return 0
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    resolve = observe.model_resolver(schema.read_table(schema.CROSSWALK))
    slug_ids = permaslug_ids(archived_listings())
    rows = []
    for i, (start, end) in enumerate(spans(FIRST_DAY, yesterday)):
        if i:
            time.sleep(2.5)
        url = f"{ENDPOINT}?start_date={start}&end_date={end}"
        raw = fetch.get_bytes(url, headers={"Authorization": f"Bearer {key}"})
        schema.write_snapshot(SOURCE, f"rankings-daily_{start}_{end}.json", raw, url)
        payload = json.loads(raw)
        rows += usage_rows(payload, url, resolve, slug_ids)
        print(f"{SOURCE}: {start}..{end}: {len(payload['data'])} rows, as of {payload['meta']['as_of']}")
    days = {r["date"] for r in rows}
    missing = (yesterday - FIRST_DAY).days + 1 - len(days)
    if missing:
        print(f"{SOURCE}: {missing} days between {FIRST_DAY} and {yesterday} have no rows")
    schema.write_table(schema.USAGE_OBSERVATIONS, rows, schema.OBSERVATIONS_DIR)
    mapped = sum(1 for r in rows if r["model_id"])
    print(f"{SOURCE}: {len(rows)} rows over {len(days)} days, {mapped} mapped to a ledger model")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
