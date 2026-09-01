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
Rows that resolve to no model are counted, not invented.
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import match
import orgs_seed
import schema
from confidence import Claim, flatten_claims, group_claims, upsert_machine_event
from schema import CLAIMS, EVENTS

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


def _model_key(model_ref: str) -> str:
    ref = model_ref.split("/")[-1]
    ref = ENGINE_SUFFIX_RE.sub("", ref)
    return match.normalize_name(ref)["key"]


def _resolve(model_ref: str, models_by_id: dict) -> str:
    key = _model_key(model_ref)
    if not key:
        return ""
    for variant in match.key_variants(key):
        if variant in models_by_id:
            return variant
    org = orgs_seed.resolve_org(key.split("-")[0])
    slug = match.slug_for(key, org) if org else key
    return slug if slug in models_by_id else ""


def _read(source: str) -> list:
    try:
        path = schema.latest_snapshot_dir(source) / "normalized.csv"
    except FileNotFoundError:
        return []
    if not path.exists():
        return []
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


def main() -> int:
    tables = schema.load_core()
    models_by_id = {m["model_id"]: m for m in tables["models"]}
    events = tables["events"]
    event_index = {(e["model_id"], e["event_type"], e.get("platform", "")): e for e in events}
    claims_by_event = group_claims(tables["claims"])
    today = date.today()

    # (model_id, platform) -> {host: [(date, model_ref, row)]}
    grouped: dict = defaultdict(lambda: defaultdict(list))
    unresolved = Counter()
    for source in ("azure_lifecycle", "bedrock_lifecycle", "litellm"):
        for row in _read(source):
            model_id = _resolve(row["model_ref"], models_by_id)
            if not model_id:
                unresolved[source] += 1
                continue
            platform = _platform_for(row, models_by_id[model_id]["developer_org_id"])
            if platform is None:
                continue
            grouped[(model_id, platform)][source].append(
                (date.fromisoformat(row["retire_date"]), row["model_ref"], row))

    outcomes = Counter()
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

    schema.write_table(EVENTS, events)
    schema.write_table(CLAIMS, flatten_claims(claims_by_event))
    print(f"lifecycle: retired events added={outcomes['added']} updated={outcomes['updated']} "
          f"unchanged={outcomes['unchanged']} curated-skipped={outcomes['skipped']}; "
          f"unresolved refs: {dict(unresolved)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
