"""Reconcile matched Tier-1 claims into core tables + disagreement report.

For every model matched across >=2 sources with a resolvable organization
and an in-scope model type, drafts an organizations row (from the curated
seed), a models row, crosswalk rows, an attributes row (models.dev serving
metadata), and dated events. Every event date goes through
`confidence.assess`, so the confidence column follows one policy:

- models.dev `release_date` -> `weights_released` when models.dev marks the
  model open-weights, else `api_ga`. The date must come from the vendor's
  own provider entry or a strict majority of resellers; disagreement with
  no majority yields no claim and a review-queue row. A lone Jan-1 date is
  stored at precision=year rather than pretending to be a day.
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
- OpenRouter expiration -> first-party `retired` on platform=openrouter
  (far-future sentinels ignored).
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
import repair
import schema
from confidence import (
    Claim, curated_announcement, earliest_availability, flatten_claims,
    group_claims, upsert_machine_event, withdraw_machine_announced_after,
    withdraw_machine_event,
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

# Review rows collected during a run; main() writes them to the shared queue.
pending_review: list = []


def _queue(kind: str, left_key: str, note: str, right_key: str = "") -> None:
    pending_review.append({"kind": kind, "left_source": "models_dev", "left_key": left_key,
                           "right_source": "ledger", "right_key": right_key, "score": "",
                           "note": note})



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
        for variant in match.key_variants(key, identity=True):
            index.setdefault(variant, key)
    return index


def _infer_model_type(modalities_in: str, modalities_out: str) -> str:
    """Model type from catalog modalities; "" when the product emits no
    text at all (music, speech synthesis, pure image generation). Image
    generators that also return a text channel are excluded by name in
    match.OUT_OF_SCOPE_RE."""
    mod_in = set(filter(None, modalities_in.split("|")))
    mod_out = set(filter(None, modalities_out.split("|")))
    if not mod_in and not mod_out:
        return "llm"  # no modality metadata: a catalog entry is a text model until shown otherwise
    if mod_out and "text" not in mod_out:
        return ""  # a language model produces text; music/TTS/image generators do not
    if mod_out - {"text"}:
        return "multimodal"  # LLMs that also emit images or speech
    if mod_in == {"text"}:
        return "llm"
    if mod_in & {"image", "video"}:
        return "vlm"
    if "audio" in mod_in:
        return "multimodal"
    return "llm"


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


def out_of_scope(row: dict) -> bool:
    """A cluster the ledger does not track: an alias, a named out-of-scope
    product, or a catalog entry whose modalities make it a generator."""
    key = row["match_key"]
    if match.is_alias_key(key) or match.is_out_of_scope_key(key):
        return True
    return bool(row["md_model_key"]) and not _infer_model_type(
        row["md_modalities_in"], row["md_modalities_out"])


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
    if out_of_scope(row):
        return None  # a moving alias or a product the ledger does not track
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
    model_type = _infer_model_type(row["md_modalities_in"], row["md_modalities_out"]) or "llm"

    model_id = match.slug_for(row["match_key"], org_id)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    md_dates = match.parse_votes(row["md_release_dates"])
    stated, basis = match.stated_release(md_dates, org_id)
    open_weights = match.open_weights_vote(match.parse_votes(row["md_open_weights_votes"]), org_id)
    derivative = schema.derivative_from_name(model_id, org_id)

    model = {
        "model_id": model_id,
        "canonical_name": row["epoch_model"] or row["md_model_key"].split("/")[-1] or row["or_id"],
        "variant_role": "",  # build.py fills from the name
        "developer_org_id": org_id,
        "model_type": model_type,
        "access_type": "open_weights" if open_weights else "api_only",
        "license": "" if open_weights else "proprietary",
        "license_family": "" if open_weights else "proprietary",
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
    # The models.dev date needs the vendor's own entry or a reseller
    # majority; when resellers disagree with no majority, no date is claimed
    # and the case goes to review rather than into the ledger.
    md_date = _parse(stated) if stated else None
    if md_dates and not stated:
        _queue("md_no_consensus", row["md_model_key"],
               f"resellers disagree: {match.serialize_votes(match._votes(md_dates))}", model_id)
    if md_date and md_date > today:
        md_date = None  # future-dated aggregator claim: not loadable
    if md_date:
        # Jan-1 dates in models.dev are year placeholders.
        precision = "year" if stated.endswith("-01-01") else "day"
        events.append({
            "event_type": "weights_released" if open_weights else "api_ga",
            "platform": "",
            "claims": [Claim(md_date, MODELS_DEV_URL, "api_metadata",
                             precision=precision, label=f"models.dev ({basis})")],
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
    expiration = _parse(row["or_expiration"])
    if expiration and (expiration - today).days < EXPIRATION_SENTINEL_HORIZON_DAYS:
        # OpenRouter's expiry is the truth about OpenRouter's listing, nothing more.
        events.append({"event_type": "retired", "platform": "openrouter",
                       "claims": [Claim(expiration, OPENROUTER_URL, "api_metadata",
                                        first_party=True, label="openrouter expiration")]})
    if vendor_rec and vendor_rec["shutdown"] and all(vendor_rec["shutdown"]):
        shutdown = max(filter(None, (_parse(d) for d in vendor_rec["shutdown"])), default=None)
        if shutdown:
            events.append({"event_type": "retired", "platform": "",
                           "claims": [Claim(shutdown, vendor_rec["url"], "api_metadata",
                                            first_party=True, label=f"{vendor_rec['source']} shutdown")]})

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
    # Identity lookup: a machine identifier already crosswalked to a model
    # pins the cluster to that model - never draft a second row.
    identity = {(r["namespace"], r["identifier"]): r["model_id"]
                for r in tables["crosswalk"]
                if r["namespace"] in schema.IDENTITY_NAMESPACES}
    attributes_by_id = {r["model_id"]: r for r in tables["attributes"]}
    events = tables["events"]
    event_index = {(e["model_id"], e["event_type"], e.get("platform", "")): e for e in events}
    claims_by_event = group_claims(tables["claims"])

    added_models = 0
    outcomes = Counter()
    touched: set = set()
    descoped: set = set()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for row in matched:
        key_hit = next((vendor_index[v] for v in match.key_variants(row["match_key"], identity=True)
                        if v in vendor_index), None)
        cluster_vendor = {row["match_key"]: vendor[key_hit]} if key_hit else None
        draft = reconcile_cluster(row, today, cluster_vendor)
        if draft is None:
            if out_of_scope(row):
                # A row drafted from this cluster on an earlier run, before the
                # scope rule caught it, goes; curated rows are never touched.
                for ns, ident in (("openrouter", row["or_id"]), ("epoch", row["epoch_model"]),
                                  ("models_dev", f"{row['md_provider']}/{row['md_model_key']}")):
                    mid = identity.get((ns, ident)) if ident else None
                    if mid and models_by_id.get(mid, {}).get("notes") == \
                            "from catalog metadata; identity and lineage unreviewed" \
                            and models_by_id[mid]["review_status"] in ("unreviewed", "machine_corroborated"):
                        descoped.add(mid)
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
                existing = next((v for v in match.key_variants(model_id, identity=True)
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
                touched.add(model_id)
            if xw["namespace"] in schema.IDENTITY_NAMESPACES:
                identity.setdefault((xw["namespace"], xw["identifier"]), model_id)

        if draft["attributes"] and model_id not in attributes_by_id:
            draft["attributes"]["model_id"] = model_id
            attributes_by_id[model_id] = draft["attributes"]
            outcomes["attributes"] += 1
            touched.add(model_id)

        floor = curated_announcement(event_index, model_id)
        # models.dev's open-weights verdict decides whether its date is a
        # weights or an API event; a row of the other type that rests on
        # models.dev alone is stale and goes first, so the announced claim
        # below is judged against current availability only.
        md_types = {e["event_type"] for e in draft["events"]
                    if any(c.label.startswith("models.dev") for c in e["claims"])}
        for stale in {"api_ga", "weights_released"} - md_types:
            if withdraw_machine_event(events, event_index, claims_by_event, model_id, stale,
                                      only_hosts={"models.dev"}):
                outcomes["stale-type-withdrawn"] += 1
                touched.add(model_id)
        # Availability first, so the announced claim can be checked against
        # every availability date on record (incl. the Hub census's).
        for ev in sorted(draft["events"], key=lambda e: e["event_type"] == "announced"):
            if ev["event_type"] == "announced":
                ceiling = earliest_availability(event_index, model_id)
                if ceiling is not None and ev["claims"][0].date > ceiling:
                    outcomes["announced-after-availability"] += 1
                    if withdraw_machine_announced_after(
                            events, event_index, claims_by_event, model_id, ceiling):
                        touched.add(model_id)
                    continue
            outcome = upsert_machine_event(
                events, event_index, claims_by_event, model_id, ev["event_type"],
                ev["claims"], today, platform=ev["platform"],
                not_before=floor if ev["event_type"] in ("api_ga", "weights_released") else None,
                next_id=schema.next_event_id)
            outcomes[outcome] += 1
            if outcome in ("added", "updated", "precreated"):
                touched.add(model_id)
        # A catalog may move availability in front of an `announced` row
        # drafted on an earlier run; the same rule applies to the stored row.
        ceiling = earliest_availability(event_index, model_id)
        if ceiling is not None and withdraw_machine_announced_after(
                events, event_index, claims_by_event, model_id, ceiling):
            outcomes["announced-after-availability"] += 1
            touched.add(model_id)

    # A catalog that stops supporting a date leaves a machine-drafted row
    # with no availability or announcement: no date, no row (rule 6).
    anchors = {"announced", "platform_availability", "api_ga", "weights_released",
               "consumer_rollout", "api_preview", "free_tier"}
    anchored = {e["model_id"] for e in events if e["event_type"] in anchors}
    orphans = {m["model_id"] for m in models_by_id.values()
               if m["model_id"] not in anchored and m["review_status"] in ("unreviewed", "machine_corroborated")
               and m["notes"] == "from catalog metadata; identity and lineage unreviewed"}
    outcomes["descoped-withdrawn"] += len(descoped - orphans)
    orphans |= descoped
    if orphans:
        working = {"models": list(models_by_id.values()), "events": events,
                   "claims": flatten_claims(claims_by_event), "crosswalk": tables["crosswalk"],
                   "attributes": list(attributes_by_id.values())}
        repair.delete_models(working, orphans)
        models_by_id = {m["model_id"]: m for m in working["models"]}
        events = working["events"]
        claims_by_event = group_claims(working["claims"])
        tables["crosswalk"] = working["crosswalk"]
        attributes_by_id = {a["model_id"]: a for a in working["attributes"]}
        outcomes["undatable-withdrawn"] += len(orphans - descoped)

    schema.mark_updated(models_by_id, touched, now)
    schema.write_table(ORGANIZATIONS, list(orgs_by_id.values()))
    schema.write_table(MODELS, list(models_by_id.values()))
    schema.write_table(EVENTS, events)
    schema.write_table(CLAIMS, flatten_claims(claims_by_event))
    schema.write_table(CROSSWALK, tables["crosswalk"])
    schema.write_table(ATTRIBUTES, list(attributes_by_id.values()))

    schema.merge_review_queue(pending_review, replace_kinds=("md_no_consensus",))
    report = write_disagreement_report(matched)
    print(f"reconcile: +{added_models} models; events added={outcomes['added']} "
          f"updated={outcomes['updated']} unchanged={outcomes['unchanged']} "
          f"curated-skipped={outcomes['skipped']} precreated-dropped={outcomes['precreated']} "
          f"undatable-withdrawn={outcomes['undatable-withdrawn']} "
          f"descoped-withdrawn={outcomes['descoped-withdrawn']}; "
          f"+{outcomes['attributes']} attributes; "
          f"vendor APIs: {sorted({v['source'] for v in vendor.values()})}; "
          f"orgs={len(orgs_by_id)}; report -> {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
