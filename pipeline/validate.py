"""Validation for llm-ledger core tables and generated artifacts.

Implements the ten rules in this module. Exits nonzero when any rule
fails. Warnings (rule 4's scheduled-future `retired` events) are printed but
do not fail the run.

Usage:
    python pipeline/validate.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import schema
from schema import (
    ACCESS_TYPES, ATTRIBUTES, AVAILABILITY_EVENT_TYPES, BOOL_VALUES,
    CONFIDENCES, CORE_TABLES, CROSSWALK, CROSSWALK_NAMESPACES,
    DERIVATIVE_TYPES, EPOCH_FORBIDDEN_COLUMN_TOKENS, EVENTS, EVENT_TYPES,
    FALLBACK_AVAILABILITY_EVENT_TYPES, FEATURE_ADDED_DETAILS,
    FIRST_AVAILABILITY_VIA, LICENSE_FAMILIES, MODALITIES, MODELS, MODEL_TYPES,
    ORGANIZATIONS, ORG_TYPES, PRECISIONS, REASONING_TYPES,
    REASONING_VISIBILITY, REVIEW_STATUSES, SOURCE_TYPES, VARIANT_ROLES,
    date_matches_precision,
)

# Event chain that must be non-decreasing in time (rule 4).
ORDER_CHAIN = ("announced", "preview", "api_preview", "api_ga")
# Availability that precedes the announcement by more than this is bad data
# (an aggregator date or a pre-created repo), not a quiet launch.
ANNOUNCE_LAG_ERROR_DAYS = 30


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def check_rule1_keys(tables: dict) -> list:
    """PK uniqueness on all tables; all FKs resolve."""
    errors = []
    for table in CORE_TABLES:
        seen = set()
        for row in tables[table.name]:
            key = tuple(row.get(c, "") for c in table.pk)
            if any(not part for part in key):
                errors.append(f"rule1: {table.name} row with empty PK component: {key}")
            elif key in seen:
                errors.append(f"rule1: {table.name} duplicate PK {key}")
            seen.add(key)

    org_ids = {r["org_id"] for r in tables["organizations"]}
    model_ids = {r["model_id"] for r in tables["models"]}

    for row in tables["organizations"]:
        parent = row.get("parent_org_id", "")
        if parent and parent not in org_ids:
            errors.append(f"rule1: org {row['org_id']} parent_org_id '{parent}' unresolved")

    model_fk_cols = (
        "base_model_id", "parent_model_id", "snapshot_of",
        "predecessor_id", "successor_id",
    )
    for row in tables["models"]:
        dev = row.get("developer_org_id", "")
        if dev not in org_ids:
            errors.append(f"rule1: model {row['model_id']} developer_org_id '{dev}' unresolved")
        for co_dev in filter(None, row.get("co_developer_org_ids", "").split("|")):
            if co_dev not in org_ids:
                errors.append(f"rule1: model {row['model_id']} co-developer '{co_dev}' unresolved")
        for col in model_fk_cols:
            ref = row.get(col, "")
            if ref and ref not in model_ids:
                errors.append(f"rule1: model {row['model_id']} {col} '{ref}' unresolved")

    for name in ("events", "crosswalk", "attributes"):
        for row in tables[name]:
            if row["model_id"] not in model_ids:
                errors.append(f"rule1: {name} references unknown model_id '{row['model_id']}'")

    event_ids = {r["event_id"] for r in tables["events"]}
    for row in tables.get("claims", []):
        if row["event_id"] not in event_ids:
            errors.append(f"rule1: claims references unknown event_id '{row['event_id']}'")
    return errors


def check_rule2_required_event_fields(tables: dict) -> list:
    """Every event: valid source_url, non-empty precision and confidence."""
    errors = []
    for row in tables["events"]:
        eid = row["event_id"]
        if not _is_url(row.get("source_url", "")):
            errors.append(f"rule2: event {eid} source_url missing or invalid: '{row.get('source_url', '')}'")
        if not row.get("precision"):
            errors.append(f"rule2: event {eid} missing precision")
        if not row.get("confidence"):
            errors.append(f"rule2: event {eid} missing confidence")
        if not row.get("region"):
            errors.append(f"rule2: event {eid} missing region")
    return errors


def check_rule3_date_precision(tables: dict) -> list:
    errors = []
    for row in tables["events"]:
        if row.get("precision") in PRECISIONS:
            if not date_matches_precision(row.get("date", ""), row["precision"]):
                errors.append(
                    f"rule3: event {row['event_id']} date '{row.get('date', '')}' "
                    f"inconsistent with precision '{row['precision']}'"
                )
    return errors


def check_rule4_temporal_sanity(tables: dict, today: date) -> tuple:
    """Ordering constraints per model+region; future events fail except retired."""
    errors, warnings = [], []
    by_model_region: dict = {}
    scheduled = 0
    for row in tables["events"]:
        try:
            d = date.fromisoformat(row.get("date", ""))
        except ValueError:
            continue  # rule 3 already reports malformed dates
        by_model_region.setdefault((row["model_id"], row.get("region", "global")), []).append((row, d))

        if d > today:
            if row["event_type"] == "retired":
                scheduled += 1
            else:
                errors.append(f"rule4: event {row['event_id']} ({row['event_type']}) dated in the future: {d}")
    if scheduled:
        warnings.append(f"rule4: {scheduled} retired event(s) are scheduled in the future "
                        "(published shutdown dates)")

    for (model_id, region), items in by_model_region.items():
        firsts = {}
        for row, d in items:
            et = row["event_type"]
            if et not in firsts or d < firsts[et]:
                firsts[et] = d
        for i, earlier in enumerate(ORDER_CHAIN):
            for later in ORDER_CHAIN[i + 1:]:
                if earlier in firsts and later in firsts and firsts[earlier] > firsts[later]:
                    errors.append(
                        f"rule4: model {model_id} ({region}): {earlier} {firsts[earlier]} "
                        f"after {later} {firsts[later]}"
                    )
        if "deprecation_announced" in firsts and "retired" in firsts:
            if firsts["deprecation_announced"] > firsts["retired"]:
                errors.append(
                    f"rule4: model {model_id} ({region}): deprecation_announced "
                    f"{firsts['deprecation_announced']} after retired {firsts['retired']}"
                )
        if "announced" in firsts:
            availability = [
                (firsts[et], et) for et in
                AVAILABILITY_EVENT_TYPES | FALLBACK_AVAILABILITY_EVENT_TYPES | {"platform_availability"}
                if et in firsts
            ]
            if availability:
                first_avail, via = min(availability)
                lag = (firsts["announced"] - first_avail).days
                msg = (f"rule4: model {model_id} ({region}): {via} {first_avail} "
                       f"precedes announced {firsts['announced']} by {lag}d")
                if lag > ANNOUNCE_LAG_ERROR_DAYS:
                    errors.append(msg)
                elif lag > 0:
                    warnings.append(msg)
    return errors, warnings


def check_rule5_confidence_contracts(tables: dict) -> list:
    errors = []
    for row in tables["events"]:
        eid = row["event_id"]
        if row.get("confidence") == "disputed" and not row.get("notes", "").strip():
            errors.append(f"rule5: disputed event {eid} has empty notes")
        if row.get("confidence") == "verified":
            if not row.get("verified_by"):
                errors.append(f"rule5: verified event {eid} missing verified_by")
            if not row.get("verified_date"):
                errors.append(f"rule5: verified event {eid} missing verified_date")
    return errors


def check_rule6_model_coverage(tables: dict) -> list:
    errors = []
    events_by_model: dict = {}
    for row in tables["events"]:
        events_by_model.setdefault(row["model_id"], set()).add(row["event_type"])
    anchor_types = (
        {"announced", "platform_availability"} | AVAILABILITY_EVENT_TYPES
        | FALLBACK_AVAILABILITY_EVENT_TYPES
    )
    for row in tables["models"]:
        mid = row["model_id"]
        types = events_by_model.get(mid, set())
        if not types:
            errors.append(f"rule6: model {mid} has no events")
        elif row.get("is_derivative", "false") != "true" and not (types & anchor_types):
            errors.append(f"rule6: non-derivative model {mid} lacks announced/availability events")
    return errors


def check_rule7_acyclic_lineage(tables: dict) -> list:
    errors = []
    edges: dict = {}
    for row in tables["models"]:
        for col in ("snapshot_of", "base_model_id", "parent_model_id"):
            ref = row.get(col, "")
            if ref:
                edges.setdefault(row["model_id"], set()).add(ref)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {mid: WHITE for mid in {r["model_id"] for r in tables["models"]}}

    def dfs(node: str, path: list) -> None:
        color[node] = GRAY
        for nxt in edges.get(node, ()):
            if color.get(nxt, BLACK) == GRAY:
                errors.append(f"rule7: lineage cycle involving {' -> '.join(path + [node, nxt])}")
            elif color.get(nxt) == WHITE:
                dfs(nxt, path + [node])
        color[node] = BLACK

    for mid in sorted(color):
        if color[mid] == WHITE:
            dfs(mid, [])
    return errors


def check_rule8_vocabularies(tables: dict) -> list:
    """Controlled-vocab columns contain only allowed values."""
    errors = []

    def check(kind: str, key: str, value: str, allowed: set, required: bool = False) -> None:
        if not value:
            if required:
                errors.append(f"rule8: {kind} {key} missing required value")
            return
        if value not in allowed:
            errors.append(f"rule8: {kind} {key} invalid value '{value}' (allowed: {sorted(allowed)})")

    for row in tables["organizations"]:
        key = f"org {row['org_id']}"
        check(key, "org_type", row.get("org_type", ""), ORG_TYPES, required=True)
        check(key, "is_active", row.get("is_active", ""), BOOL_VALUES, required=True)

    for row in tables["models"]:
        key = f"model {row['model_id']}"
        check(key, "variant_role", row.get("variant_role", ""), VARIANT_ROLES, required=True)
        check(key, "model_type", row.get("model_type", ""), MODEL_TYPES, required=True)
        check(key, "access_type", row.get("access_type", ""), ACCESS_TYPES, required=True)
        check(key, "license_family", row.get("license_family", ""), LICENSE_FAMILIES)
        check(key, "is_derivative", row.get("is_derivative", ""), BOOL_VALUES, required=True)
        check(key, "derivative_type", row.get("derivative_type", ""), DERIVATIVE_TYPES)
        check(key, "first_availability_via", row.get("first_availability_via", ""), FIRST_AVAILABILITY_VIA)
        check(key, "review_status", row.get("review_status", ""), REVIEW_STATUSES, required=True)
        for col in ("license_has_usage_thresholds", "license_requires_separate_agreement"):
            check(key, col, row.get(col, ""), BOOL_VALUES)
        if row.get("is_derivative") == "true" and not row.get("derivative_type"):
            errors.append(f"rule8: model {row['model_id']} is_derivative without derivative_type")

    for row in tables["events"]:
        key = f"event {row['event_id']}"
        check(key, "event_type", row.get("event_type", ""), EVENT_TYPES, required=True)
        check(key, "precision", row.get("precision", ""), PRECISIONS, required=True)
        check(key, "source_type", row.get("source_type", ""), SOURCE_TYPES, required=True)
        check(key, "confidence", row.get("confidence", ""), CONFIDENCES, required=True)
        # `platform` is required for platform_availability and optional
        # elsewhere (a retirement on Azure is not a retirement at OpenAI).
        if row.get("event_type") == "platform_availability" and not row.get("platform"):
            errors.append(f"rule8: {key} platform_availability requires platform")
        if row.get("event_type") == "feature_added":
            check(key, "detail", row.get("detail", ""), FEATURE_ADDED_DETAILS, required=True)
        expected_prefix = f"{row.get('model_id', '')}-{row.get('event_type', '')}-"
        if not (row["event_id"].startswith(expected_prefix)
                and row["event_id"][len(expected_prefix):].isdigit()):
            errors.append(f"rule8: {key} id does not follow {{model_id}}-{{event_type}}-{{seq}}")

    for row in tables["crosswalk"]:
        key = f"crosswalk {row['model_id']}/{row['namespace']}"
        check(key, "namespace", row.get("namespace", ""), CROSSWALK_NAMESPACES, required=True)

    for row in tables.get("claims", []):
        key = f"claim {row['event_id']}/{row['source_url']}"
        check(key, "source_type", row.get("source_type", ""), SOURCE_TYPES, required=True)
        for col in ("bound", "first_party"):
            check(key, col, row.get(col, ""), BOOL_VALUES, required=True)
        if not _is_url(row.get("source_url", "")):
            errors.append(f"rule8: {key} source_url invalid")
        if not date_matches_precision(row.get("date", ""), "day"):
            errors.append(f"rule8: {key} date '{row.get('date', '')}' is not ISO")

    for row in tables["attributes"]:
        key = f"attributes {row['model_id']}"
        # reasoning_type is optional: catalogs say whether a model reasons,
        # not how, and the ledger does not guess.
        check(key, "reasoning_type", row.get("reasoning_type", ""), REASONING_TYPES)
        check(key, "reasoning_tokens_visible", row.get("reasoning_tokens_visible", ""), REASONING_VISIBILITY)
        for col in ("reasoning_supported", "reasoning_tokens_billed",
                    "reasoning_is_separate_checkpoint", "supports_tool_use",
                    "supports_structured_output", "supports_caching"):
            check(key, col, row.get(col, ""), BOOL_VALUES)
        for col in ("modality_in", "modality_out"):
            for modality in filter(None, row.get(col, "").split("|")):
                check(key, col, modality, MODALITIES)
    return errors


def check_rule9_determinism(core_dir: Path) -> list:
    """Wide/enriched artifacts regenerate byte-identically from core tables."""
    import build  # local import: build depends on schema only

    errors = []
    for filename, regenerate in (
        ("llm_ledger_wide.csv", build.build_wide_bytes),
        ("llm_ledger_enriched.csv", build.build_enriched_bytes),
    ):
        path = schema.GENERATED_DIR / filename
        if not path.exists():
            continue  # artifact not built yet; nothing to compare
        try:
            fresh = regenerate()
        except FileNotFoundError:
            # Raw dumps are not redistributed (manifests only), so a fresh
            # clone cannot rerun this comparison; `make pull` restores it.
            continue
        if fresh != path.read_bytes():
            errors.append(f"rule9: {filename} is not byte-identical to a fresh rebuild")
    return errors


def check_rule10_no_epoch_columns(tables: dict) -> list:
    errors = []
    for table in CORE_TABLES:
        for col in table.columns:
            lowered = col.lower()
            for token in EPOCH_FORBIDDEN_COLUMN_TOKENS:
                if token in lowered:
                    errors.append(f"rule10: core table {table.name} carries Epoch-domain column '{col}'")
    return errors


def validate_tables(tables: dict, today: date, core_dir: Path = schema.CORE_DIR,
                    check_determinism: bool = True) -> tuple:
    errors: list = []
    warnings: list = []
    errors += check_rule1_keys(tables)
    errors += check_rule2_required_event_fields(tables)
    errors += check_rule3_date_precision(tables)
    e4, w4 = check_rule4_temporal_sanity(tables, today)
    errors += e4
    warnings += w4
    errors += check_rule5_confidence_contracts(tables)
    errors += check_rule6_model_coverage(tables)
    errors += check_rule7_acyclic_lineage(tables)
    errors += check_rule8_vocabularies(tables)
    if check_determinism:
        errors += check_rule9_determinism(core_dir)
    errors += check_rule10_no_epoch_columns(tables)
    return errors, warnings


def main() -> int:
    tables = schema.load_core()
    errors, warnings = validate_tables(tables, today=date.today())

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    counts = ", ".join(f"{name}={len(rows)}" for name, rows in tables.items())
    if errors:
        print(f"\nvalidate: FAILED with {len(errors)} error(s), {len(warnings)} warning(s) [{counts}]")
        return 1
    print(f"validate: OK ({len(warnings)} warning(s)) [{counts}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
