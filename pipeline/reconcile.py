"""Reconcile matched Tier-1 claims into core tables + disagreement report.

For every model matched across >=2 sources with a resolvable organization
and an in-scope model type, drafts an organizations row (from the curated
seed), a models row, crosswalk rows, an attributes row (models.dev serving
metadata), and dated events. Every event date goes through
`confidence.assess`, so the confidence column follows one policy:

- models.dev `release_date` -> `weights_released` when models.dev marks the
  model open-weights, else `api_ga`. A lone Jan-1 date is stored at
  precision=year rather than pretending to be a day.
- vendor `/models` APIs (OpenAI `created`, Anthropic `created_at`) ->
  `api_ga` claims. These are registry timestamps that precede the public
  launch by days, so they corroborate a catalog date but do not verify on
  their own. OpenAI `shutdown_date` is a published schedule -> first-party
  `retired` claim.
- any machine availability claim dated before a curated `announced` event
  is private pre-staging (repo or model object created ahead of launch):
  not loaded, and a stale machine row is withdrawn.
- OpenRouter `created` -> its own `platform_availability` (platform=
  openrouter) row: the platform's own timestamp for its own event.
- OpenRouter expiration -> `retired` claim (far-future sentinels ignored).
- Epoch publication date -> `announced`, only when it does not fall after
  any availability date (Epoch's "publication" is the earliest of
  paper/announcement/release, which is not always an announcement).

Machine-owned rows (source_type hf_hub / api_metadata) are re-assessed on
every run so aggregator corrections propagate; curated rows are never
touched. Also writes data/generated/disagreement_report.md.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import match
import orgs_seed
import schema
from confidence import (
    Claim, curated_announcement, earliest_availability, flatten_claims,
    group_claims, upsert_machine_event, withdraw_machine_announced_after,
)
from schema import ATTRIBUTES, CLAIMS, CROSSWALK, EVENTS, MODELS, ORGANIZATIONS

MODELS_DEV_URL = "https://models.dev/api.json"
OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
EPOCH_URL = "https://epoch.ai/data/all_ai_models.csv"

# Vendor list APIs: source -> (org_id whose models they describe, URL).
VENDOR_APIS = {
    "openai_api": ("openai", "https://api.openai.com/v1/models"),
    "anthropic_api": ("anthropic", "https://api.anthropic.com/v1/models"),
    "google_api": ("google", "https://generativelanguage.googleapis.com/v1beta/models"),
    "mistral_api": ("mistral", "https://api.mistral.ai/v1/models"),
}

# OpenRouter uses far-future expiration sentinels for "no planned shutdown".
EXPIRATION_SENTINEL_HORIZON_DAYS = 3 * 365

IN_SCOPE_TYPES = {"llm", "vlm", "multimodal"}

VARIANT_TOKENS = ("mini", "nano", "pro", "thinking", "instruct", "chat", "coder", "vision")


def _read_matched() -> list:
    path = schema.GENERATED_DIR / "matched_models.csv"
    if not path.exists():
        raise FileNotFoundError(f"run pipeline/match.py first: {path} missing")
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_vendor_apis() -> dict:
    """match key -> {source, org_id, url, ids, created, shutdown}.

    Snapshot ids (gpt-4o-2024-08-06) fold into their model key; the
    model's API availability is the earliest `created` across its ids, and
    it is retired only when every id carries a shutdown date (the latest).
    Vendors without a snapshot on disk are simply absent.
    """
    by_key: dict = {}
    for source, (org_id, url) in VENDOR_APIS.items():
        try:
            snap = schema.latest_snapshot_dir(source) / "normalized.csv"
        except FileNotFoundError:
            continue
        if not snap.exists():
            continue
        with snap.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                key = match.normalize_name(row["id"])["key"]
                if not key:
                    continue
                entry = by_key.setdefault(key, {
                    "source": source, "org_id": org_id, "url": url,
                    "ids": [], "created": [], "shutdown": [],
                })
                entry["ids"].append(row["id"])
                entry["created"].append(row["created_date"])
                entry["shutdown"].append(row["shutdown_date"])
    return by_key


def _vendor_index(vendor: dict) -> dict:
    index = {}
    for key in vendor:
        for variant in match.key_variants(key):
            index.setdefault(variant, key)
    return index


def _infer_model_type(modalities_in: str, modalities_out: str) -> str:
    mod_in = set(filter(None, modalities_in.split("|")))
    mod_out = set(filter(None, modalities_out.split("|")))
    if not mod_in or "text" not in mod_out and mod_out:
        return ""  # image/audio/video generators are out of scope
    if mod_out - {"text"}:
        return "multimodal"
    if mod_in == {"text"} or not mod_in:
        return "llm"
    if "image" in mod_in or "video" in mod_in:
        return "vlm"
    if "audio" in mod_in:
        return "multimodal"
    return "llm"


def _variant_role(match_key: str) -> str:
    tokens = match_key.split("-")
    for token in VARIANT_TOKENS:
        if token in tokens:
            return token
    return "other"


def _parse(d: str) -> date | None:
    try:
        return date.fromisoformat(d)
    except ValueError:
        return None


def _attributes_from_models_dev(model_id: str, row: dict) -> dict:
    """Serving metadata models.dev publishes; reasoning *type* is not
    inferable from its boolean, so only `reasoning_supported` is filled."""
    reasoning = row["md_reasoning"]
    return {
        "model_id": model_id,
        "reasoning_supported": reasoning if reasoning in ("true", "false") else "",
        "reasoning_type": "none" if reasoning == "false" else "",
        "context_length": row["md_context_length"],
        "max_output_tokens": row["md_max_output_tokens"],
        "modality_in": row["md_modalities_in"],
        "modality_out": row["md_modalities_out"],
        "knowledge_cutoff": row["md_knowledge_cutoff"],
        "supports_tool_use": row["md_tool_call"] if row["md_tool_call"] in ("true", "false") else "",
        "price_input": row["md_cost_input"],
        "price_output": row["md_cost_output"],
        "price_cached_input": row["md_cost_cache_read"],
        "price_date": row["md_snapshot_date"],
        "source_url": MODELS_DEV_URL,
    }


def reconcile_cluster(row: dict, today: date, vendor: dict | None = None) -> dict | None:
    """Turn one matched cluster into draft core rows, or None if out of scope.

    Returns {"org_id", "model", "crosswalk", "attributes", "events"} where each
    event is {"event_type", "platform", "precision", "claims": [Claim]}; the
    caller runs the claims through the confidence policy against existing
    rows.
    """
    sources = row["sources"].split("|")
    if len(sources) < 2:
        return None
    # Attribution priority: OpenRouter's curated vendor namespace, then the
    # model-family token from the name itself (nemotron beats llama), then
    # the models.dev key prefix / provider (may be a reseller).
    first_token = row["match_key"].split("-")[0]
    family_tokens = ("nemotron",) if "nemotron" in row["match_key"] else (
        first_token, first_token.rstrip("0123456789"))
    org_id = orgs_seed.resolve_org(
        row["or_prefix"], *family_tokens, row["md_prefix"], row["md_provider"])
    if not org_id:
        return None
    model_type = _infer_model_type(row["md_modalities_in"], row["md_modalities_out"])
    if row["md_model_key"] and not model_type:
        return None  # confidently out of scope (image/audio generator)
    model_type = model_type or "llm"

    model_id = match.slug_for(row["match_key"], org_id)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    open_weights = row["md_open_weights"] == "true"
    derivative = schema.derivative_from_name(model_id)

    model = {
        "model_id": model_id,
        "canonical_name": row["epoch_model"] or row["md_model_key"].split("/")[-1] or row["or_id"],
        "variant_role": _variant_role(row["match_key"]),
        "developer_org_id": org_id,
        "model_type": model_type,
        "access_type": "open_weights" if open_weights else "api_only",
        "is_derivative": "true" if derivative else "false",
        "derivative_type": derivative,
        "review_status": "unreviewed",
        "record_created": now,
        "record_updated": now,
        "notes": "from catalog metadata; identity and lineage unreviewed",
    }

    crosswalk = []
    if row["md_model_key"]:
        crosswalk.append({"model_id": model_id, "namespace": "models_dev",
                          "identifier": f"{row['md_provider']}/{row['md_model_key']}"})
    if row["or_id"]:
        crosswalk.append({"model_id": model_id, "namespace": "openrouter",
                          "identifier": row["or_id"]})
    if row["epoch_model"]:
        crosswalk.append({"model_id": model_id, "namespace": "epoch",
                          "identifier": row["epoch_model"]})

    vendor_rec = (vendor or {}).get(row["match_key"])
    if vendor_rec and vendor_rec["org_id"] != org_id:
        vendor_rec = None  # a vendor API only speaks for its own models
    if vendor_rec:
        for ident in vendor_rec["ids"]:
            crosswalk.append({"model_id": model_id, "namespace": vendor_rec["source"],
                              "identifier": ident})

    events = []

    # --- availability -------------------------------------------------------
    # models.dev serializes a missing release date as the unix epoch.
    md_date = None if row["md_release_date"] == "1970-01-01" else _parse(row["md_release_date"])
    if md_date and md_date > today:
        md_date = None  # future-dated aggregator claim: not loadable
    if md_date:
        # Jan-1 dates in models.dev are year placeholders.
        precision = "year" if row["md_release_date"].endswith("-01-01") else "day"
        events.append({
            "event_type": "weights_released" if open_weights else "api_ga",
            "platform": "",
            "claims": [Claim(md_date, MODELS_DEV_URL, "api_metadata",
                             precision=precision, label="models.dev")],
        })

    vendor_dates = sorted(filter(None, (_parse(d) for d in vendor_rec["created"]))) if vendor_rec else []
    vendor_dates = [d for d in vendor_dates if d <= today]
    if vendor_dates:
        # Vendor registries stamp `created` when the model object is
        # registered, which precedes the public launch by days (observed:
        # 1-16d for OpenAI and Anthropic). A lower bound, so not first-party.
        claim = Claim(vendor_dates[0], vendor_rec["url"], "api_metadata",
                      bound=True, label=f"{vendor_rec['source']} created")
        api_ga = next((e for e in events if e["event_type"] == "api_ga"), None)
        if api_ga:
            api_ga["claims"].append(claim)
        else:
            events.append({"event_type": "api_ga", "platform": "",
                           "claims": [claim]})

    or_date = _parse(row["or_created"])
    if or_date and or_date <= today:
        events.append({
            "event_type": "platform_availability", "platform": "openrouter",
            "claims": [Claim(or_date, OPENROUTER_URL, "api_metadata",
                             first_party=True, label="openrouter")],
        })

    # --- announced ------------------------------------------------------------
    epoch_date = _parse(row["epoch_publication_date"])
    availability = [c.date for e in events for c in e["claims"]]
    if epoch_date and epoch_date <= today and all(epoch_date <= d for d in availability):
        events.append({
            "event_type": "announced", "platform": "",
            "claims": [Claim(epoch_date, EPOCH_URL, "api_metadata", label="epoch.ai")],
        })

    # --- retirement -----------------------------------------------------------
    retired_claims = []
    expiration = _parse(row["or_expiration"])
    if expiration and (expiration - today).days < EXPIRATION_SENTINEL_HORIZON_DAYS:
        retired_claims.append(Claim(expiration, OPENROUTER_URL, "api_metadata",
                                    label="openrouter expiration"))
    if vendor_rec and vendor_rec["shutdown"] and all(vendor_rec["shutdown"]):
        shutdown = max(filter(None, (_parse(d) for d in vendor_rec["shutdown"])), default=None)
        if shutdown:
            retired_claims.append(Claim(shutdown, vendor_rec["url"], "api_metadata",
                                        first_party=True, label=f"{vendor_rec['source']} shutdown"))
    if retired_claims:
        events.append({"event_type": "retired", "platform": "",
                       "claims": retired_claims})

    if not events:
        return None  # no dated claim -> no row (rule: no date, no event)
    attributes = _attributes_from_models_dev(model_id, row) if row["md_model_key"] else None
    return {"org_id": org_id, "model": model, "crosswalk": crosswalk,
            "attributes": attributes, "events": events}


def write_disagreement_report(matched: list) -> Path:
    lines = [
        "# Cross-source disagreement report",
        "",
        "Comparing, per matched model: the models.dev `release_date` (mode",
        "across providers), the OpenRouter `created` listing date, and the",
        "Epoch AI publication date. Generated by `pipeline/reconcile.py`.",
        "",
    ]
    multi = [r for r in matched if "|" in r["sources"]]

    deltas = []
    for r in multi:
        dates = {
            "models_dev": _parse(r["md_release_date"]),
            "openrouter": _parse(r["or_created"]),
            "epoch": _parse(r["epoch_publication_date"]),
        }
        present = {k: v for k, v in dates.items() if v}
        if len(present) < 2:
            continue
        worst = max(
            abs((a - b).days)
            for i, a in enumerate(present.values())
            for b in list(present.values())[i + 1:]
        )
        deltas.append((worst, r, present))

    histogram = Counter()
    for worst, _, _ in deltas:
        for label, upper in (("0d", 0), ("1-2d", 2), ("3-7d", 7), ("8-30d", 30),
                             ("31-90d", 90), (">90d", 10 ** 9)):
            if worst <= upper:
                histogram[label] += 1
                break

    lines += [
        f"- Matched clusters: {len(matched)} total, {len(multi)} across >=2 sources",
        f"- Clusters with >=2 comparable dates: {len(deltas)}",
        "",
        "## Distribution of worst pairwise |delta| per model",
        "",
        "| bucket | models |",
        "|---|---|",
    ]
    for label in ("0d", "1-2d", "3-7d", "8-30d", "31-90d", ">90d"):
        lines.append(f"| {label} | {histogram.get(label, 0)} |")

    lines += [
        "",
        "## Top 50 largest disagreements",
        "",
        "| model | models.dev | openrouter | epoch | worst delta (d) |",
        "|---|---|---|---|---|",
    ]
    deltas.sort(key=lambda item: (-item[0], item[1]["match_key"]))
    for worst, r, _ in deltas[:50]:
        lines.append(
            f"| {r['match_key']} | {r['md_release_date'] or '-'} | "
            f"{r['or_created'] or '-'} | {r['epoch_publication_date'] or '-'} | {worst} |"
        )
    lines.append("")

    path = schema.GENERATED_DIR / "disagreement_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    matched = _read_matched()
    today = date.today()
    vendor = load_vendor_apis()
    vendor_index = _vendor_index(vendor)

    tables = schema.load_core()
    orgs_by_id = {r["org_id"]: r for r in tables["organizations"]}
    models_by_id = {r["model_id"]: r for r in tables["models"]}
    crosswalk_keys = {(r["model_id"], r["namespace"], r["identifier"])
                      for r in tables["crosswalk"]}
    # Identity lookup: an epoch/openrouter identifier already crosswalked to
    # a model pins the cluster to that model - never draft a second row.
    identity = {(r["namespace"], r["identifier"]): r["model_id"]
                for r in tables["crosswalk"]
                if r["namespace"] in ("epoch", "openrouter")}
    attributes_by_id = {r["model_id"]: r for r in tables["attributes"]}
    events = tables["events"]
    event_index = {(e["model_id"], e["event_type"], e.get("platform", "")): e for e in events}
    claims_by_event = group_claims(tables["claims"])

    added_models = 0
    outcomes = Counter()
    for row in matched:
        key_hit = next((vendor_index[v] for v in match.key_variants(row["match_key"])
                        if v in vendor_index), None)
        cluster_vendor = {row["match_key"]: vendor[key_hit]} if key_hit else None
        draft = reconcile_cluster(row, today, cluster_vendor)
        if draft is None:
            continue

        for seed in orgs_seed.SEED_ORGS:
            if seed["org_id"] == draft["org_id"] and seed["org_id"] not in orgs_by_id:
                orgs_by_id[seed["org_id"]] = dict(seed)

        model_id = draft["model"]["model_id"]
        if model_id not in models_by_id:
            # Already-crosswalked identifiers pin the cluster to an existing
            # model; failing that, a spelling variant may exist (vendor
            # "qwen2-5-..." vs aggregator "qwen-2-5-..."). Only draft a new
            # row when neither resolves.
            existing = next(
                (identity[(xw["namespace"], xw["identifier"])]
                 for xw in draft["crosswalk"]
                 if (xw["namespace"], xw["identifier"]) in identity), None)
            if not existing:
                existing = next((v for v in match.key_variants(model_id)
                                 if v in models_by_id), None)
            if existing:
                model_id = existing
            else:
                models_by_id[model_id] = draft["model"]
                added_models += 1

        for xw in draft["crosswalk"]:
            xw["model_id"] = model_id
            key = (xw["model_id"], xw["namespace"], xw["identifier"])
            if key not in crosswalk_keys:
                crosswalk_keys.add(key)
                tables["crosswalk"].append(xw)
            if xw["namespace"] in ("epoch", "openrouter"):
                identity.setdefault((xw["namespace"], xw["identifier"]), model_id)

        if draft["attributes"] and model_id not in attributes_by_id:
            draft["attributes"]["model_id"] = model_id
            attributes_by_id[model_id] = draft["attributes"]
            outcomes["attributes"] += 1

        floor = curated_announcement(event_index, model_id)
        # Availability first, so the announced claim can be checked against
        # every availability date on record (incl. the Hub census's).
        for ev in sorted(draft["events"], key=lambda e: e["event_type"] == "announced"):
            if ev["event_type"] == "announced":
                ceiling = earliest_availability(event_index, model_id)
                if ceiling is not None and ev["claims"][0].date > ceiling:
                    outcomes["announced-after-availability"] += 1
                    withdraw_machine_announced_after(
                        events, event_index, claims_by_event, model_id, ceiling)
                    continue
            outcome = upsert_machine_event(
                events, event_index, claims_by_event, model_id, ev["event_type"],
                ev["claims"], today, platform=ev["platform"],
                not_before=floor if ev["event_type"] in ("api_ga", "weights_released") else None,
                next_id=schema.next_event_id)
            outcomes[outcome] += 1

    schema.write_table(ORGANIZATIONS, list(orgs_by_id.values()))
    schema.write_table(MODELS, list(models_by_id.values()))
    schema.write_table(EVENTS, events)
    schema.write_table(CLAIMS, flatten_claims(claims_by_event))
    schema.write_table(CROSSWALK, tables["crosswalk"])
    schema.write_table(ATTRIBUTES, list(attributes_by_id.values()))

    report = write_disagreement_report(matched)
    print(f"reconcile: +{added_models} models; events added={outcomes['added']} "
          f"updated={outcomes['updated']} unchanged={outcomes['unchanged']} "
          f"curated-skipped={outcomes['skipped']} precreated-dropped={outcomes['precreated']}; "
          f"+{outcomes['attributes']} attributes; "
          f"vendor APIs: {sorted({v['source'] for v in vendor.values()})}; "
          f"orgs={len(orgs_by_id)}; report -> {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
