"""Reconcile matched Tier-1 claims into core tables + disagreement report.

For every model matched across >=2 sources with a resolvable organization
and an in-scope model type, drafts (idempotently - existing rows are never
touched, verified rows never overwritten):

- an organizations row (from the curated seed),
- a models row,
- crosswalk rows (models_dev / openrouter / epoch identifiers),
- an `api_ga` event from the models.dev release date, corroborated or
  disputed by the OpenRouter listing date,
- an `announced` event from the Epoch publication date (only when it does
  not contradict the availability date - Epoch's "publication" is the
  earliest of paper/announcement/release, which is not always an
  announcement),
- a scheduled `retired` event when OpenRouter carries a real expiration
  date (far-future sentinel values are ignored).

All drafted events carry confidence=inferred (or disputed), because these
are aggregator claims, not primary-source verifications.

Also writes data/generated/disagreement_report.md over the whole matched
population, regardless of what was loaded.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import match
import orgs_seed
import schema
from schema import ATTRIBUTES, CROSSWALK, EVENTS, MODELS, ORGANIZATIONS

MODELS_DEV_URL = "https://models.dev/api.json"
OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
EPOCH_URL = "https://epoch.ai/data/all_ai_models.csv"

# Days beyond which two same-precision availability claims are a dispute
# rather than expected aggregator listing lag.
DISPUTE_THRESHOLD_DAYS = 30
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


def reconcile_cluster(row: dict, today: date) -> dict | None:
    """Turn one matched cluster into draft core rows, or None if out of scope."""
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

    model = {
        "model_id": model_id,
        "canonical_name": row["epoch_model"] or row["md_model_key"].split("/")[-1] or row["or_id"],
        "variant_role": _variant_role(row["match_key"]),
        "developer_org_id": org_id,
        "model_type": model_type,
        "access_type": "open_weights" if row["md_open_weights"] == "true" else "api_only",
        "is_derivative": "false",
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

    events = []
    # models.dev serializes a missing release date as the unix epoch.
    md_date = None if row["md_release_date"] == "1970-01-01" else _parse(row["md_release_date"])
    or_date = _parse(row["or_created"])
    if md_date and md_date > today:
        md_date = None  # future-dated aggregator claim: not loadable
    if or_date and or_date > today:
        or_date = None

    if md_date and or_date:
        delta = abs((or_date - md_date).days)
        md_is_placeholder = row["md_release_date"].endswith("-01-01") and delta > DISPUTE_THRESHOLD_DAYS
        if delta > DISPUTE_THRESHOLD_DAYS:
            best = or_date if (md_is_placeholder or or_date < md_date) else md_date
            events.append({
                "event_type": "api_ga", "date": best.isoformat(),
                "source_url": MODELS_DEV_URL if best == md_date else OPENROUTER_URL,
                "confidence": "disputed",
                "notes": (
                    f"conflicting aggregator claims: models.dev release_date "
                    f"{row['md_release_date']} ({MODELS_DEV_URL}) vs OpenRouter "
                    f"listing date {row['or_created']} ({OPENROUTER_URL}); "
                    f"kept {best.isoformat()}"
                    + (" because the models.dev value looks like a Jan-1 placeholder"
                       if md_is_placeholder else
                       " as the earlier evidenced availability" if best == or_date
                       else " as the curated release-date claim")
                ),
            })
        else:
            events.append({
                "event_type": "api_ga", "date": md_date.isoformat(),
                "source_url": MODELS_DEV_URL, "confidence": "inferred",
                "notes": f"models.dev release_date; OpenRouter listing followed "
                         f"{row['or_created']} (lag {delta}d)",
            })
    elif md_date:
        events.append({
            "event_type": "api_ga", "date": md_date.isoformat(),
            "source_url": MODELS_DEV_URL, "confidence": "inferred",
            "notes": "models.dev release_date; no second aggregator claim",
        })
    elif or_date:
        events.append({
            "event_type": "api_ga", "date": or_date.isoformat(),
            "source_url": OPENROUTER_URL, "confidence": "inferred",
            "notes": "OpenRouter listing date; lower bound on availability",
        })

    epoch_date = _parse(row["epoch_publication_date"])
    availability = _parse(events[0]["date"]) if events else None
    if epoch_date and epoch_date <= today and (availability is None or epoch_date <= availability):
        events.append({
            "event_type": "announced", "date": epoch_date.isoformat(),
            "source_url": EPOCH_URL, "confidence": "inferred",
            "notes": "Epoch AI publication date (earliest of paper/announcement/"
                     "release per Epoch); verify against the vendor's own channel",
        })

    expiration = _parse(row["or_expiration"])
    if expiration and (expiration - today).days < EXPIRATION_SENTINEL_HORIZON_DAYS:
        events.append({
            "event_type": "retired", "date": expiration.isoformat(),
            "source_url": OPENROUTER_URL, "confidence": "inferred",
            "notes": "scheduled shutdown per OpenRouter expiration metadata; "
                     "verify against the vendor deprecation page",
        })

    if not events:
        return None  # no dated claim -> no row (rule: no date, no event)
    return {"org_id": org_id, "model": model, "crosswalk": crosswalk, "events": events}


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
    events = tables["events"]
    event_type_present = {(e["model_id"], e["event_type"]) for e in events}

    added_models = added_events = 0
    for row in matched:
        draft = reconcile_cluster(row, today)
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
                (identity[(ns, xw["identifier"])]
                 for xw in draft["crosswalk"]
                 for ns in (xw["namespace"],)
                 if (ns, xw["identifier"]) in identity), None)
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

        for ev in draft["events"]:
            # Idempotency + append-only: if this model already has an event
            # of this type (from any earlier run or a human), leave it alone.
            if (model_id, ev["event_type"]) in event_type_present:
                continue
            # An aggregator api_ga claim is a lower bound on availability; it
            # is only informative when the ledger has no availability-class
            # event for the model yet. Otherwise it re-adds claims a verifier
            # already resolved into a more precise event type.
            if ev["event_type"] == "api_ga" and any(
                (model_id, et) in event_type_present
                for et in ("weights_released", "consumer_rollout",
                           "platform_availability", "api_preview", "free_tier")):
                continue
            event_type_present.add((model_id, ev["event_type"]))
            events.append({
                "event_id": schema.next_event_id(events, model_id, ev["event_type"]),
                "model_id": model_id,
                "event_type": ev["event_type"],
                "date": ev["date"],
                "precision": "day",
                "region": "global",
                "source_type": "api_metadata",
                "source_url": ev["source_url"],
                "confidence": ev["confidence"],
                "notes": ev["notes"],
            })
            added_events += 1

    schema.write_table(ORGANIZATIONS, list(orgs_by_id.values()))
    schema.write_table(MODELS, list(models_by_id.values()))
    schema.write_table(EVENTS, events)
    schema.write_table(CROSSWALK, tables["crosswalk"])

    report = write_disagreement_report(matched)
    print(f"reconcile: +{added_models} models, +{added_events} events, "
          f"orgs={len(orgs_by_id)}; report -> {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
