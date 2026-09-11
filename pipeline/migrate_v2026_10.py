"""One-time repair of the v2026.09 data to the v2026.10 policy.

    python pipeline/migrate_v2026_10.py --dry-run   # counts only
    python pipeline/migrate_v2026_10.py             # apply, then run loaders

Idempotent: every step selects rows by rule, so a second run finds nothing.
After applying, run: make match reconcile census lifecycle build validate
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hf_census
import match
import repair
import schema
from confidence import MACHINE_SOURCE_TYPES
from pull_hf import NAMESPACE_TO_ORG

CENSUS_NOTE = "from Hugging Face census; identity and lineage unreviewed"
CATALOG_NOTE = "from catalog metadata; identity and lineage unreviewed"
MACHINE_NOTES = {CENSUS_NOTE, CATALOG_NOTE}
PLATFORM_RENAMES = {"aws_bedrock": "bedrock", "gcp_vertex": "vertex", "azure_openai": "azure"}
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")


def _machine_models(tables: dict) -> list:
    """Rows no curator has touched: drafted by a loader, never curated."""
    return [m for m in tables["models"]
            if m["review_status"] in ("unreviewed", "machine_corroborated")
            and m["notes"] in MACHINE_NOTES]


def _claims_by_event(tables: dict) -> dict:
    out: dict = {}
    for c in tables["claims"]:
        out.setdefault(c["event_id"], []).append(c)
    return out


def step_platforms(tables: dict, log: Counter) -> None:
    for old, new in PLATFORM_RENAMES.items():
        log[f"platform {old}->{new}"] += repair.retag_platform(tables, old, new)
    claims_by_event = _claims_by_event(tables)
    for e in tables["events"]:
        labels = {c["label"].split(" (")[0] for c in claims_by_event.get(e["event_id"], [])}
        if e["event_type"] == "retired" and e["platform"] == "" and labels == {"openrouter expiration"}:
            e["platform"] = "openrouter"  # reconcile re-assesses it as first-party
            for c in claims_by_event[e["event_id"]]:
                c["first_party"] = "true"
            log["openrouter expiration scoped"] += 1


def step_claims(tables: dict, log: Counter) -> None:
    claimed = {c["event_id"] for c in tables["claims"]}
    for e in list(tables["events"]):
        if e["source_type"] in MACHINE_SOURCE_TYPES and e["event_id"] not in claimed:
            label = "epoch.ai" if "epoch.ai" in e["source_url"] else e["source_url"].split("/")[2]
            repair.backfill_single_claim(tables, e["event_id"], label)
            log["claims backfilled"] += 1
        elif e["source_type"] == "wayback" and e["event_id"] in claimed:
            if repair.reset_to_hub_claim(tables, e["event_id"], date.today()):
                log["wayback rows reset to hub claim"] += 1
            else:
                log["capture-only rows dropped"] += 1


def step_scope(tables: dict, log: Counter) -> None:
    gone = {m["model_id"] for m in _machine_models(tables)
            if match.is_alias_key(m["model_id"]) or match.is_out_of_scope_key(m["model_id"])}
    VERBOSE.extend(f"delete (scope): {g}" for g in sorted(gone))
    log["aliases/out-of-scope deleted"] += repair.delete_models(tables, gone)


def step_formats(tables: dict, log: Counter) -> None:
    ids = {m["model_id"] for m in tables["models"]}
    for m in _machine_models(tables):
        old_id = m["model_id"]
        norm = match.normalize_name(old_id)
        if not norm["format_suffix"]:
            continue
        base = match.slug_for(norm["key"], m["developer_org_id"])
        if base in ids:
            VERBOSE.append(f"merge (format): {old_id} -> {base}")
            repair.merge_models(tables, keep=base, drop=old_id)
            log["format variants merged"] += 1
        else:
            VERBOSE.append(f"rename (format): {old_id} -> {base}")
            repair.rename_model(tables, old_id, base)  # mutates m["model_id"]
            ids.add(base)
            log["format variants renamed"] += 1
        ids.discard(old_id)


def step_mirrors_and_roles(tables: dict, log: Counter) -> None:
    """Rows drafted from another lab's mirror are deleted (the census
    re-drafts them from the official repo); mirror repos attached to a real
    row are detached; repos whose identity key differs from the model's
    (base vs instruct) are detached so the census splits them."""
    by_model: dict = {}
    for r in tables["crosswalk"]:
        if r["namespace"] == "huggingface":
            by_model.setdefault(r["model_id"], []).append(r["identifier"])
    gone = set()
    for m in _machine_models(tables):
        org = m["developer_org_id"]
        mk = match.normalize_name(m["model_id"])["key"]  # packaging suffix stripped
        same_keys = set(match.key_variants(mk, identity=True))

        def is_same(repo_key: str) -> bool:
            return repo_key in same_keys or match.slug_for(repo_key, org) == m["model_id"]

        repos = by_model.get(m["model_id"], [])
        has_base_repo = any(is_same(match.normalize_name(r)["key"]) for r in repos)
        for repo in repos:
            norm = match.normalize_name(repo)
            ns_org = NAMESPACE_TO_ORG.get(repo.split("/")[0], "")
            is_mirror = bool(ns_org) and hf_census.classify(norm["key"], ns_org) == "mirror"
            if is_mirror and ns_org == org:
                gone.add(m["model_id"])  # the row itself was drafted from a mirror
            elif is_mirror:
                VERBOSE.append(f"detach (mirror): {m['model_id']} <- {repo}")
                repair.detach_crosswalk(tables, m["model_id"], "huggingface", repo)
                log["mirror repos detached"] += 1
            elif is_same(norm["key"]):
                continue
            elif has_base_repo and any(v in same_keys for v in match.key_variants(norm["key"])):
                # an instruct/chat repo sharing a row with its base checkpoint
                VERBOSE.append(f"detach (role): {m['model_id']} <- {repo}")
                repair.detach_crosswalk(tables, m["model_id"], "huggingface", repo)
                log["role-variant repos detached"] += 1
            else:
                VERBOSE.append(f"keep (unmatched key): {m['model_id']} <- {repo}")
                log["unmatched repo keys kept"] += 1
    VERBOSE.extend(f"delete (mirror-drafted): {g}" for g in sorted(gone))
    log["mirror-drafted models deleted"] += repair.delete_models(tables, gone)
    # weights events whose claim came from a detached repo are dropped; the
    # census re-upserts from the repos that remain.
    kept = {(r["model_id"], r["identifier"]) for r in tables["crosswalk"] if r["namespace"] == "huggingface"}
    for e in list(tables["events"]):
        if e["event_type"] == "weights_released" and e["source_type"] == "hf_hub":
            repo = e["source_url"].removeprefix("https://huggingface.co/")
            if (e["model_id"], repo) not in kept:
                tables["events"].remove(e)
                tables["claims"] = [c for c in tables["claims"] if c["event_id"] != e["event_id"]]
                log["weights events from detached repos dropped"] += 1


def step_identifier_splits(tables: dict, log: Counter) -> None:
    # Verified by hand in the 2026-09-10 audit.
    if any(m["model_id"] == "mistral-7b-v0-1" for m in tables["models"]):
        repair.merge_models(tables, "mistral-7b", "mistral-7b-v0-1")  # same checkpoint, two ids
        log["identifier splits merged"] += 1
    for ident in ("gpt-5.2", "gpt-5.2-2025-12-11"):
        if repair.detach_crosswalk(tables, "gpt-5-2-chat", "openai_api", ident):
            log["misattached vendor ids detached"] += 1
    for m in tables["models"]:
        if m["model_id"] == "gpt-3-5-turbo" and not m["parent_model_id"]:
            m["parent_model_id"], m["record_updated"] = "gpt-3-5", NOW
            log["gpt-3-5-turbo parented"] += 1


def step_model_fields(tables: dict, log: Counter) -> None:
    for m in _machine_models(tables):
        changed = False
        if m["access_type"] == "api_only" and not m["license_family"]:
            m["license"], m["license_family"], changed = "proprietary", "proprietary", True
            log["api-only license filled"] += 1
        elif m["license"] and schema.license_family(m["license"]) != m["license_family"]:
            m["license_family"], changed = schema.license_family(m["license"]), True
            log["license_family recomputed"] += 1
        derivative = schema.derivative_from_name(m["model_id"], m["developer_org_id"])
        if derivative and m["is_derivative"] != "true":
            m["is_derivative"], m["derivative_type"], changed = "true", derivative, True
            log["derivatives flagged"] += 1
        if changed:
            m["record_updated"] = NOW


# Mirrors go before packaging merges: a mirror-drafted "llama-2-70b-hf" must
# be deleted, not folded into the curated llama-2-70b as a format variant.
STEPS = (step_platforms, step_claims, step_scope, step_mirrors_and_roles, step_formats,
         step_identifier_splits, step_model_fields)
VERBOSE: list = []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true", help="list every row deleted, merged or renamed")
    args = parser.parse_args()
    tables = schema.load_core()
    log: Counter = Counter()
    for step in STEPS:
        step(tables, log)
    if args.verbose:
        for line in VERBOSE:
            print(f"migrate: {line}")
    for k, v in sorted(log.items()):
        print(f"migrate: {k}: {v}")
    if args.dry_run:
        return 0
    for table in schema.CORE_TABLES:
        schema.write_table(table, tables[table.name])
    print("migrate: core tables written; now run: make match reconcile census lifecycle build validate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
