"""Load platform retirement schedules into `retired` events.

Reads the normalized pull_lifecycle.py snapshots and, for every row whose
model_ref resolves to a ledger model, upserts a machine-owned `retired`
event through the shared confidence policy:

- Azure and Bedrock publish their own schedules: first-party claims for a
  retirement scoped to that platform (`platform=azure|bedrock`).
- LiteLLM copies provider schedules: a corroborating (non-first-party)
  claim. When its provider is the model's own vendor the retirement is
  global (platform=""); otherwise it is scoped to the provider.

A model with several versions on a platform is retired there when the LAST
version is; the latest date wins and the versions are listed in the label.
A row names its model by exact id first (the crosswalk), by name second;
when the two disagree it goes to the review queue. Rows that resolve to no
model are counted, not invented.
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import match
import orgs_seed
import schema
from confidence import Claim, flatten_claims, group_claims, index_events, upsert_machine_event
from schema import CLAIMS, EVENTS, MODELS

# LiteLLM provider slugs that are hosting platforms, not model vendors.
PLATFORM_PROVIDERS = {
    "bedrock": "bedrock", "bedrock_converse": "bedrock", "azure": "azure",
    "azure_ai": "azure", "vertex_ai": "vertex", "vertex_ai-language-models": "vertex",
    "fireworks_ai": "fireworks", "together_ai": "together", "groq": "groq",
    "deepinfra": "deepinfra", "openrouter": "openrouter", "sagemaker": "sagemaker",
}
# LiteLLM provider slugs that ARE the vendor: retirement is global.
VENDOR_PROVIDERS = {"openai": "openai", "anthropic": "anthropic", "gemini": "google",
                    "mistral": "mistral", "cohere": "cohere", "cohere_chat": "cohere",
                    "xai": "xai", "deepseek": "deepseek", "ai21": "ai21"}

# Bedrock/LiteLLM ids carry a trailing engine version (-v1:0, -v2) that is
# not part of the model's identity.
ENGINE_SUFFIX_RE = re.compile(r"(-v\d+(:\d+)?|:\d+)$")

# Azure Foundry lists SKUs served by a partner under a prefix. The event
# stays on platform=azure (it is Azure's schedule); the partner goes in
# `detail`, so no host that nothing else in the ledger uses appears as a
# platform.
SERVING_PARTNERS = {"FW": "Fireworks AI"}
PARTNER_PREFIX_RE = re.compile(r"^(" + "|".join(SERVING_PARTNERS) + r")-", re.IGNORECASE)

# Review rows collected during a run; main() writes them to the shared queue.
pending_review: list = []


def _serving_partner(model_ref: str) -> str:
    m = PARTNER_PREFIX_RE.match(model_ref.split("/")[-1])
    return SERVING_PARTNERS[m.group(1).upper()] if m else ""


def _model_key(model_ref: str) -> str:
    ref = model_ref.split("/")[-1]
    ref = PARTNER_PREFIX_RE.sub("", ref)
    ref = ENGINE_SUFFIX_RE.sub("", ref)
    return match.normalize_name(ref)["key"]


def crosswalk_index(crosswalk: list) -> dict:
    """identifier (last path segment, lower-cased) -> {model_id} over the
    identity namespaces; the exact ids catalogs and vendor registries use."""
    index: dict = defaultdict(set)
    for row in crosswalk:
        if row["namespace"] in schema.IDENTITY_NAMESPACES:
            index[row["identifier"].split("/")[-1].lower()].add(row["model_id"])
    return index


def _resolve_by_name(key: str, models_by_id: dict) -> str:
    for variant in match.key_variants(key, identity=True):
        if variant in models_by_id:
            return variant
    org = orgs_seed.resolve_org(key.split("-")[0])
    slug = match.slug_for(key, org) if org else key
    return slug if slug in models_by_id else ""


def _resolve(model_ref: str, models_by_id: dict, xw_index: dict) -> tuple:
    """(model_id, conflict): a crosswalk hit on the exact id wins; with none,
    the name is matched; when both exist and disagree nothing is picked and
    the pair comes back as `conflict` for the review queue. Name-only
    matching once sent Azure's `o3-2025-04-16` nowhere while the crosswalk
    already knew the id."""
    ref = PARTNER_PREFIX_RE.sub("", model_ref.split("/")[-1]).lower()
    by_id = {m for cand in (ref, ENGINE_SUFFIX_RE.sub("", ref)) for m in xw_index.get(cand, ())}
    by_id = {m for m in by_id if m in models_by_id}
    key = _model_key(model_ref)
    by_name = _resolve_by_name(key, models_by_id) if key else ""
    if by_name and by_name in by_id:
        # One id may map to a model and its dated snapshots (rule 12); the
        # name says which of them the row means.
        return by_name, ""
    if len(by_id) == 1:
        (hit,) = by_id
        if by_name and by_name != hit:
            return "", f"crosswalk:{hit}|name:{by_name}"
        return hit, ""
    if len(by_id) > 1:
        return "", "crosswalk:" + ",".join(sorted(by_id))
    return by_name, ""


def _read(source: str) -> list:
    try:
        path = schema.snapshot_file(source, "normalized.csv")
    except FileNotFoundError:
        return []  # a source never pulled contributes nothing; a stale one raises
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _platform_for(row: dict, developer_org: str) -> str | None:
    """Platform scope for a claim, or None when the row is not usable."""
    if row["source"] != "litellm":
        return row["platform"]
    provider = row["platform"]
    if provider in VENDOR_PROVIDERS:
        return "" if VENDOR_PROVIDERS[provider] == developer_org else None
    return PLATFORM_PROVIDERS.get(provider)


SOURCES = ("azure_lifecycle", "bedrock_lifecycle", "litellm")


def load(rows_by_source: dict, tables: dict, today: date, now: str) -> Counter:
    """Upsert `retired` events into `tables` (mutated in place) from the
    normalized lifecycle rows of each source; `now` stamps record_updated
    on touched models. Returns outcome counts plus `unresolved:<source>`
    for rows naming no ledger model."""
    models_by_id = {m["model_id"]: m for m in tables["models"]}
    xw_index = crosswalk_index(tables.get("crosswalk", []))
    events = tables["events"]
    event_index = index_events(events)
    claims_by_event = group_claims(tables["claims"])

    # (model_id, platform) -> {source: [(date, model_ref, row)]}
    grouped: dict = defaultdict(lambda: defaultdict(list))
    outcomes: Counter = Counter()
    for source, rows in rows_by_source.items():
        for row in rows:
            model_id, conflict = _resolve(row["model_ref"], models_by_id, xw_index)
            if conflict:
                pending_review.append({
                    "kind": "lifecycle_ambiguous", "left_source": source,
                    "left_key": row["model_ref"], "right_source": "ledger",
                    "right_key": conflict, "score": "",
                    "note": "exact-id crosswalk and name matching name different models; "
                            "add the id to crosswalk.csv for the right one"})
                outcomes[f"ambiguous:{source}"] += 1
                continue
            if not model_id:
                outcomes[f"unresolved:{source}"] += 1
                continue
            platform = _platform_for(row, models_by_id[model_id]["developer_org_id"])
            if platform is None:
                continue
            grouped[(model_id, platform)][source].append(
                (date.fromisoformat(row["retire_date"]), row["model_ref"], row))

    touched: set = set()
    for (model_id, platform), by_source in sorted(grouped.items()):
        claims = []
        for source, entries in by_source.items():
            entries.sort(key=lambda e: (e[0], e[1]))
            last_date, _, row = entries[-1]
            versions = ", ".join(e[1] for e in entries)
            claims.append(Claim(
                last_date, row["url"],
                "lifecycle_table" if source != "litellm" else "api_metadata",
                first_party=source != "litellm",
                label=f"{source} ({versions})",
            ))
        outcome = upsert_machine_event(
            events, event_index, claims_by_event, model_id, "retired", claims, today,
            platform=platform, next_id=schema.next_event_id)
        outcomes[outcome] += 1
        if outcome in ("added", "updated"):
            touched.add(model_id)
        row = event_index.get((model_id, "retired", platform))
        partner_skus = sorted({(e[1].split("/")[-1], _serving_partner(e[1]))
                               for entries in by_source.values()
                               for e in entries if _serving_partner(e[1])})
        if row is not None and partner_skus and outcome != "skipped":
            detail = "; ".join(f"served_by={partner} ({sku})" for sku, partner in partner_skus)
            if row["detail"] != detail:
                row["detail"] = detail
                touched.add(model_id)

    schema.mark_updated(models_by_id, touched, now)
    tables["claims"] = flatten_claims(claims_by_event)
    return outcomes


def main() -> int:
    tables = schema.load_core()
    outcomes = load({source: _read(source) for source in SOURCES}, tables, date.today(),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"))
    for table in (MODELS, EVENTS, CLAIMS):
        schema.write_table(table, tables[table.name])
    schema.merge_review_queue(pending_review, replace_kinds=("lifecycle_ambiguous",))
    unresolved = {k.split(":", 1)[1]: v for k, v in outcomes.items() if k.startswith("unresolved:")}
    ambiguous = {k.split(":", 1)[1]: v for k, v in outcomes.items() if k.startswith("ambiguous:")}
    print(f"lifecycle: retired events added={outcomes['added']} updated={outcomes['updated']} "
          f"unchanged={outcomes['unchanged']} curated-skipped={outcomes['skipped']}; "
          f"unresolved refs: {unresolved}; ambiguous (review queue): {ambiguous}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
