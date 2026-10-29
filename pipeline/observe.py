"""Dated market observations from the daily raw pulls.

For each day a source was pulled, every id it lists becomes an
availability observation, and the price and serving limits it shows for
that id become price and capability observations. The version a source
states for an id (a Hub commit sha, a dated API snapshot id, Google's
`version` field) becomes a model_versions row. Values are copied as the
source states them, in the source's own unit. A row is a run: the source
showed these values on every day from `first_observed` to `last_observed`.
A day the source was not pulled ends every run; an id missing from a day
the source was pulled was not listed that day.

Usage:
    python pipeline/observe.py                 # payloads under data/raw
    python pipeline/observe.py --raw-root DIR  # an extracted raw-YYYY-MM-DD archive

A day at or before the last one a table holds for a source is skipped for
that table, so days must arrive in order, a re-run changes nothing, and a
new table backfills from archives the other tables already hold. `model_id` is re-resolved
from the crosswalk on every run.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import schema
from match import normalize_name

AVAILABILITY = schema.AVAILABILITY_OBSERVATIONS.name
PRICE = schema.PRICE_OBSERVATIONS.name
CAPABILITY = schema.CAPABILITY_OBSERVATIONS.name
VERSIONS = schema.MODEL_VERSIONS.name

VENDOR_APIS = ("openai_api", "anthropic_api", "google_api", "mistral_api")
# source -> the payload file its observations are read from
PAYLOADS = {"models_dev": "normalized.csv", "openrouter": "normalized.csv",
            "litellm": "model_prices_and_context_window.json", "hf": "normalized.csv",
            "litellm_git": "model_prices_and_context_window.json.gz",
            **{s: "normalized.csv" for s in VENDOR_APIS}}
# The manifest entry whose URL is the evidence for the day.
MANIFEST_PAYLOAD = {"models_dev": "api.json", "openrouter": "models.json",
                    "litellm": "model_prices_and_context_window.json", "hf": "normalized.csv",
                    "litellm_git": "model_prices_and_context_window.json",
                    **{s: "models.json" for s in VENDOR_APIS}}
LITELLM_SOURCES = ("litellm", "litellm_git")
# Namespaces whose identifiers name serving ids; the key fallback reads them.
SERVING_NAMESPACES = ("models_dev", "openrouter") + VENDOR_APIS


def _read_csv(path: Path) -> list:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _models_dev(rows: list, url: str) -> dict:
    out = {AVAILABILITY: [], PRICE: [], CAPABILITY: []}
    for r in rows:
        base = {"source": "models_dev", "provider": r["provider"], "api_id": r["model_key"],
                "source_url": url}
        out[AVAILABILITY].append(base)
        if r["cost_input"] or r["cost_output"] or r["cost_cache_read"]:
            out[PRICE].append(base | {
                "price_input": r["cost_input"], "price_output": r["cost_output"],
                "price_cached": r["cost_cache_read"], "currency": "USD",
                "unit": "per_1m_tokens"})
        out[CAPABILITY].append(base | {
            "context_length": r["context_length"], "max_output": r["max_output_tokens"],
            "modalities_in": r["modalities_in"], "modalities_out": r["modalities_out"],
            "tool_use": r["tool_call"], "structured_output": "", "reasoning": r["reasoning"]})
    return out


def _openrouter(rows: list, url: str) -> dict:
    out = {AVAILABILITY: [], PRICE: [], CAPABILITY: []}
    for r in rows:
        base = {"source": "openrouter", "provider": "openrouter", "api_id": r["id"],
                "source_url": url}
        out[AVAILABILITY].append(base)
        if r["price_prompt"] or r["price_completion"]:
            out[PRICE].append(base | {
                "price_input": r["price_prompt"], "price_output": r["price_completion"],
                "price_cached": "", "currency": "USD", "unit": "per_token"})
        out[CAPABILITY].append(base | {
            "context_length": r["context_length"], "max_output": "",
            "modalities_in": r["modalities_in"], "modalities_out": r["modalities_out"],
            "tool_use": "", "structured_output": "", "reasoning": ""})
    return out


def _vendor_api(source: str, rows: list, url: str, google_versions: dict) -> dict:
    """`google_versions` maps a Gemini API id to the `version` its registry
    states; the other vendors state none, so only an id that carries a
    snapshot date is a version."""
    out = {AVAILABILITY: [], PRICE: [], CAPABILITY: [], VERSIONS: []}
    provider = source.removesuffix("_api")
    for r in rows:
        base = {"source": source, "provider": provider, "api_id": r["id"], "source_url": url}
        out[AVAILABILITY].append(base)
        if r["max_input_tokens"] or r["max_output_tokens"]:
            out[CAPABILITY].append(base | {
                "context_length": r["max_input_tokens"], "max_output": r["max_output_tokens"],
                "modalities_in": "", "modalities_out": "", "tool_use": "",
                "structured_output": "", "reasoning": ""})
        # ponytail: snapshot dates are read by match.normalize_name, which knows
        # OpenAI's and Anthropic's date forms but not Mistral's YYMM suffix
        # (codestral-2508); teach it that before counting Mistral snapshots.
        version = google_versions.get(r["id"]) or (
            r["id"] if normalize_name(r["id"])["snapshot_suffix"] else "")
        if version:
            out[VERSIONS].append(base | {"version_kind": "api_snapshot", "version_id": version,
                                         "stated_date": r["created_date"]})
    return out


def _hf(rows: list, url: str) -> dict | None:
    """Hub commit per repo. Sweeps before the puller recorded `sha` hold
    none and yield nothing."""
    if not rows or "sha" not in rows[0]:
        return None
    return {VERSIONS: [
        {"source": "hf", "provider": "huggingface", "api_id": r["repo_id"],
         "version_kind": "hf_revision", "version_id": r["sha"],
         "stated_date": r["last_modified"], "source_url": url}
        for r in rows if r["sha"]]}


def _google_versions(models_json: Path) -> dict:
    """Gemini API id -> the `version` field its registry entry states."""
    payload = json.loads(models_json.read_text(encoding="utf-8"))
    entries = payload["models"] if isinstance(payload, dict) else payload
    return {m["name"].removeprefix("models/"): m["version"] for m in entries if m.get("version")}


def _flag(entry: dict, key: str) -> str:
    return "" if key not in entry else str(entry[key]).lower()


def _litellm(entries: dict, url: str, source: str = "litellm") -> dict:
    """LiteLLM's price table is a client library's copy of provider prices,
    not a provider's listing: it yields prices and limits, never availability.
    `litellm_git` is the same table read from a day's commit in its history."""
    out = {AVAILABILITY: [], PRICE: [], CAPABILITY: []}
    for api_id, e in entries.items():
        if api_id == "sample_spec" or not isinstance(e, dict):
            continue
        base = {"source": source, "provider": e.get("litellm_provider", ""),
                "api_id": api_id, "source_url": url}
        prices = (e.get("input_cost_per_token", ""), e.get("output_cost_per_token", ""),
                  e.get("cache_read_input_token_cost", ""))
        if any(prices):
            out[PRICE].append(base | {
                "price_input": prices[0], "price_output": prices[1], "price_cached": prices[2],
                "currency": "USD", "unit": "per_token"})
        limits = (e.get("max_input_tokens", ""), e.get("max_output_tokens", ""))
        if any(limits):
            out[CAPABILITY].append(base | {
                "context_length": limits[0], "max_output": limits[1],
                "modalities_in": "", "modalities_out": "",
                "tool_use": _flag(e, "supports_function_calling"),
                "structured_output": _flag(e, "supports_response_schema"),
                "reasoning": _flag(e, "supports_reasoning")})
    return out


def day_observations(source: str, day_dir: Path) -> dict | None:
    """Table name -> records for one source-day, or None when the day holds
    no payload (a failed pull, or a checkout that keeps manifests only)."""
    payload = day_dir / PAYLOADS[source]
    manifest_path = day_dir / "manifest.json"
    if not payload.exists() or not manifest_path.exists():
        return None
    entry = json.loads(manifest_path.read_text(encoding="utf-8")).get(MANIFEST_PAYLOAD[source], {})
    if "sha256" not in entry:
        return None
    url = entry["url"]
    if source in LITELLM_SOURCES:
        raw = payload.read_bytes()
        if payload.suffix == ".gz":
            raw = gzip.decompress(raw)
        # Numbers stay as written: 2.5e-06 is not re-serialized.
        entries = json.loads(raw.decode("utf-8"), parse_float=str, parse_int=str)
        return _litellm(entries, url, source)
    rows = _read_csv(payload)
    if source == "models_dev":
        return _models_dev(rows, url)
    if source == "openrouter":
        return _openrouter(rows, url)
    if source == "hf":
        return _hf(rows, url)
    google = _google_versions(day_dir / "models.json") if source == "google_api" else {}
    return _vendor_api(source, rows, url, google)


def _values(row: dict, table: schema.Table) -> tuple:
    """What a run holds constant. `source_url` is not part of it: a run
    keeps the URL of its first day, which for `litellm_git` names the
    commit where the values were first read."""
    return tuple(row.get(c, "") for c in table.columns
                 if c not in ("model_id", "first_observed", "last_observed", "source_url"))


def _subject(row: dict) -> tuple:
    return (row["source"], row["provider"], row["api_id"])


def extend_runs(rows: list, records: list, table: schema.Table, day: date) -> int:
    """Fold one source-day into a table's runs: a run that ended yesterday
    with the same values grows by a day, anything else starts a run.
    Returns the number of new runs."""
    latest: dict = {}
    for r in rows:
        if r["last_observed"] > latest.get(_subject(r), {}).get("last_observed", ""):
            latest[_subject(r)] = r
    yesterday, today = (day - timedelta(days=1)).isoformat(), day.isoformat()
    seen: dict = {}
    started = 0
    for rec in records:
        subject = _subject(rec)
        if subject in seen:
            if seen[subject] != _values(rec, table):
                raise ValueError(f"{table.name}: {subject} listed twice on {today} "
                                 "with different values")
            continue
        seen[subject] = _values(rec, table)
        prev = latest.get(subject)
        if prev is not None and prev["last_observed"] == yesterday \
                and _values(prev, table) == seen[subject]:
            prev["last_observed"] = today
            continue
        rows.append(rec | {"model_id": "", "first_observed": today, "last_observed": today})
        started += 1
    return started


def _key(identifier: str) -> str:
    norm = normalize_name(identifier.rsplit("/", 1)[-1])
    return "-".join(filter(None, (norm["key"], norm["snapshot_suffix"])))


def model_resolver(crosswalk: list):
    """(source, provider, api_id) -> model_id. An exact crosswalk identifier
    wins; else the normalized key, when it names exactly one model. A Hub
    repo resolves only exactly: the census decides which repos a model has."""
    exact = {(r["namespace"], r["identifier"]): r["model_id"] for r in crosswalk}
    by_key: dict = {}
    for r in crosswalk:
        if r["namespace"] in SERVING_NAMESPACES:
            by_key.setdefault(_key(r["identifier"]), set()).add(r["model_id"])

    def resolve(source: str, provider: str, api_id: str) -> str:
        if source == "hf":
            return exact.get(("huggingface", api_id), "")
        identifier = f"{provider}/{api_id}" if source == "models_dev" else api_id
        if (source, identifier) in exact:
            return exact[(source, identifier)]
        ids = by_key.get(_key(api_id), set())
        return next(iter(ids)) if len(ids) == 1 else ""
    return resolve


def _day_dirs(raw_root: Path) -> list:
    """(day, source, dir) for every source-day under a raw root, oldest first."""
    found = []
    for source in PAYLOADS:
        for d in sorted((raw_root / source).glob("????-??-??")):
            found.append((date.fromisoformat(d.name), source, d))
    return sorted(found)


def observe(raw_root: Path, tables: dict, crosswalk: list) -> list:
    """Fold every new source-day under `raw_root` into `tables` (name ->
    rows) and re-resolve model ids. Returns one log line per day folded."""
    last_seen: dict = {}
    for name, rows in tables.items():
        for r in rows:
            key = (name, r["source"])
            last_seen[key] = max(last_seen.get(key, ""), r["last_observed"])
    log = []
    for day, source, day_dir in _day_dirs(raw_root):
        pending = [t for t in schema.OBSERVATION_TABLES
                   if day.isoformat() > last_seen.get((t.name, source), "")]
        if not pending:
            continue
        obs = day_observations(source, day_dir)
        if obs is None:
            continue
        counts = []
        for table in pending:
            records = obs.get(table.name, [])
            if not records:
                continue
            started = extend_runs(tables[table.name], records, table, day)
            counts.append(f"{table.name.split('_')[0]} {len(records)} ({started} new runs)")
        if counts:
            log.append(f"observe: {source} {day}: " + ", ".join(counts))
    resolve = model_resolver(crosswalk)
    for rows in tables.values():
        for r in rows:
            r["model_id"] = resolve(r["source"], r["provider"], r["api_id"])
    return log


def load_observations() -> dict:
    """Name -> rows for each observation table; a table not yet written
    starts empty."""
    tables = {}
    for table in schema.OBSERVATION_TABLES:
        path = schema.OBSERVATIONS_DIR / table.filename
        tables[table.name] = schema.read_table(table, schema.OBSERVATIONS_DIR) if path.exists() else []
    return tables


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-root", type=Path, default=schema.RAW_DIR,
                        help="directory holding <source>/<YYYY-MM-DD>/ payloads")
    args = parser.parse_args()
    if not args.raw_root.is_dir():
        raise SystemExit(f"observe: no raw root at {args.raw_root}")
    tables = load_observations()
    for line in observe(args.raw_root, tables, schema.read_table(schema.CROSSWALK)):
        print(line)
    for table in schema.OBSERVATION_TABLES:
        schema.write_table(table, tables[table.name], schema.OBSERVATIONS_DIR)
        rows = tables[table.name]
        mapped = sum(1 for r in rows if r["model_id"])
        print(f"observe: {table.filename}: {len(rows)} runs, {mapped} mapped to a ledger model")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
