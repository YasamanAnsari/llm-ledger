"""Apply the inclusion rule to the HF snapshot and load the open-weight census.

Inclusion rule: a model enters the ledger if it is a distinct trained
checkpoint from an organization, released under its own name. Quantizations,
format conversions, LoRA adapters, and community merges are excluded unless
independently notable.

For each included repo:
- reuses an existing models row when the normalized name matches (adding the
  huggingface crosswalk id and a weights_released event if missing),
- otherwise drafts a new models row,
- adds a `weights_released` event dated from repo `createdAt`. Repo
  creation is a LOWER BOUND on public release (labs create repos private
  and flip them later), so on its own the claim is `inferred`. When
  pull_wayback.py has recorded the first public Wayback capture of the
  repo page and it agrees within confidence.BOUND_AGREE_DAYS, the row
  becomes `verified` by llm-ledger. The 2022-03-02 HF backfill artifact is
  queued for review, never used.
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import match as matchmod
import orgs_seed
import schema
from confidence import (
    Claim, curated_announcement, flatten_claims, group_claims,
    upsert_machine_event, withdraw_machine_announced_after,
)
from schema import CLAIMS, CROSSWALK, EVENTS, MODELS, ORGANIZATIONS

HF_BACKFILL_DATE = "2022-03-02"

# Conversion/adapter markers: these repos repackage an existing checkpoint.
EXCLUDE_NAME_RE = re.compile(
    r"(gguf|awq|gptq|exl2|onnx|openvino|mlx|-mxfp4|-nvfp4|w4a16|w8a8|"
    r"-4bit|-8bit|-fp4|-bnb|bitsandbytes|-lora|-adapter|-dpo-lora)",
    re.IGNORECASE,
)
EXCLUDE_TAGS = {"gguf", "awq", "gptq", "onnx", "mlx", "peft", "lora", "adapter"}

PER_ORG_CAP = 40  # top downloads per org; long-tail checkpoints add noise


def load_wayback_captures() -> dict:
    """repo_id -> first public Wayback capture date, from the latest
    pull_wayback snapshot; empty when none has been pulled."""
    try:
        path = schema.latest_snapshot_dir("wayback") / "normalized.csv"
    except FileNotFoundError:
        return {}
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        return {r["repo_id"]: r["first_capture_date"]
                for r in csv.DictReader(fh) if r["first_capture_date"]}


def include(row: dict) -> bool:
    if row["pipeline_tag"] not in ("text-generation", "image-text-to-text"):
        return False
    if not row["org_id"]:
        return False  # unmapped namespace: lead, not a core row
    name = row["repo_id"].split("/")[-1]
    if EXCLUDE_NAME_RE.search(name):
        return False
    tags = set(row["tags"].lower().split("|"))
    if tags & EXCLUDE_TAGS:
        return False
    return True


def main() -> int:
    snap = schema.latest_snapshot_dir("hf") / "normalized.csv"
    if not snap.exists():
        raise FileNotFoundError(f"run pipeline/pull_hf.py first: {snap} missing")
    with snap.open(newline="", encoding="utf-8") as fh:
        repos = list(csv.DictReader(fh))

    tables = schema.load_core()
    models_by_id = {m["model_id"]: m for m in tables["models"]}
    org_ids = {o["org_id"] for o in tables["organizations"]}
    hf_xw = {r["identifier"]: r["model_id"] for r in tables["crosswalk"]
             if r["namespace"] == "huggingface"}
    xw_keys = {(r["model_id"], r["namespace"], r["identifier"]) for r in tables["crosswalk"]}
    events = tables["events"]
    event_index = {(e["model_id"], e["event_type"], e.get("platform", "")): e for e in events}
    claims_by_event = group_claims(tables["claims"])
    captures = load_wayback_captures()

    review_rows = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = date.today()
    outcomes: dict = {}

    included = [r for r in repos if include(r)]
    by_org: dict = {}
    for row in included:
        by_org.setdefault(row["org_id"], []).append(row)
    # Top downloads per org enter; repos already in the ledger stay in
    # regardless of rank, so a tracked model never loses its date.
    capped = []
    for org, rows in sorted(by_org.items()):
        rows.sort(key=lambda r: -int(r["downloads"] or 0))
        capped.extend(rows[:PER_ORG_CAP])
        capped.extend(r for r in rows[PER_ORG_CAP:] if r["repo_id"] in hf_xw)

    added_models = added_events = added_xw = 0
    drafted_this_run: set = set()
    earliest_repo: dict = {}
    for row in sorted(capped, key=lambda r: r["repo_id"]):
        repo_id = row["repo_id"]
        norm = matchmod.normalize_name(repo_id)
        # Same short-key slug rule as reconcile, so "tencent/Hy3" and the
        # aggregators' "hy3" cluster land on one id (tencent-hy3).
        slug = matchmod.slug_for(norm["key"], row["org_id"])
        model_id = hf_xw.get(repo_id) or (
            slug if slug in models_by_id else "")
        # try serving-format variants against existing ids (Qwen3-235B-A22B
        # repo should reuse the qwen3-235b-a22b row, not duplicate it)
        if not model_id:
            for variant in matchmod.key_variants(norm["key"]):
                if variant in models_by_id:
                    model_id = variant
                    break
        if not model_id:
            model_id = slug
            if not model_id:
                continue
            name = repo_id.split("/")[-1]
            derivative = schema.derivative_from_name(model_id)
            models_by_id[model_id] = {
                "model_id": model_id,
                "canonical_name": name,
                "variant_role": "other",
                "developer_org_id": row["org_id"],
                "model_type": "vlm" if row["pipeline_tag"] == "image-text-to-text" else "llm",
                "access_type": "open_weights",
                "license": row["license"],
                "license_family": schema.license_family(row["license"]),
                "is_derivative": "true" if derivative else "false",
                "derivative_type": derivative,
                "review_status": "unreviewed",
                "record_created": now,
                "record_updated": now,
                "notes": "from Hugging Face census; identity and lineage unreviewed",
            }
            if row["org_id"] not in org_ids:
                seed = next((s for s in orgs_seed.SEED_ORGS if s["org_id"] == row["org_id"]), None)
                if seed:
                    tables["organizations"].append(dict(seed))
                    org_ids.add(row["org_id"])
            drafted_this_run.add(model_id)
            added_models += 1

        key = (model_id, "huggingface", repo_id)
        if key not in xw_keys:
            xw_keys.add(key)
            tables["crosswalk"].append(
                {"model_id": model_id, "namespace": "huggingface", "identifier": repo_id})
            hf_xw[repo_id] = model_id
            added_xw += 1

        if not row["created_at"]:
            continue
        if row["created_at"] == HF_BACKFILL_DATE:
            review_rows.append({
                "kind": "hf_backfill_date", "left_source": "huggingface",
                "left_key": repo_id, "right_source": "", "right_key": "",
                "score": "",
                "note": "createdAt is the HF backfill artifact; weights date "
                        "needs another primary source",
            })
            continue
        # Several repos can resolve to one model (base + refreshed variant);
        # the earliest repo is the weights release.
        if model_id not in earliest_repo or row["created_at"] < earliest_repo[model_id][0]:
            earliest_repo[model_id] = (row["created_at"], repo_id)

    for model_id, (created_at, repo_id) in sorted(earliest_repo.items()):
        existing = event_index.get((model_id, "weights_released", ""))
        if existing is not None and existing["source_type"] == "hf_hub" \
                and existing["date"] < created_at:
            continue  # an earlier repo seen on a previous run still stands
        repo_url = f"https://huggingface.co/{repo_id}"
        claims = [Claim(date.fromisoformat(created_at), repo_url, "hf_hub",
                        bound=True, label="hub repo created")]
        if repo_id in captures:
            claims.append(Claim(
                date.fromisoformat(captures[repo_id]),
                f"https://web.archive.org/web/{captures[repo_id].replace('-', '')}/{repo_url}",
                "wayback", bound=True, label="first public capture"))
        floor = curated_announcement(event_index, model_id)
        outcome = upsert_machine_event(
            events, event_index, claims_by_event, model_id, "weights_released", claims,
            today, not_before=floor, next_id=schema.next_event_id)
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        if outcome in ("added", "updated", "unchanged"):
            assessed = event_index[(model_id, "weights_released", "")]["date"]
            withdraw_machine_announced_after(
                events, event_index, claims_by_event, model_id, date.fromisoformat(assessed))
        if outcome == "added":
            added_events += 1
        elif outcome == "precreated":
            # Repo existed before the curated announcement: created private.
            review_rows.append({
                "kind": "hf_precreated_repo", "left_source": "huggingface",
                "left_key": repo_id, "right_source": "ledger", "right_key": model_id,
                "score": "",
                "note": f"repo created {created_at}, announced {floor}; "
                        "weights date needs a primary source",
            })

    # A drafted model that ended up with no datable event would violate
    # validation rule 6 (>= 1 event per model): withdraw it and keep only the
    # review-queue lead. Its date needs a human-found primary source first.
    dated = {e["model_id"] for e in events}
    undatable = {m for m in drafted_this_run if m not in dated}
    if undatable:
        for model_id in sorted(undatable):
            del models_by_id[model_id]
        n_before = len(tables["crosswalk"])
        tables["crosswalk"] = [r for r in tables["crosswalk"]
                               if r["model_id"] not in undatable]
        added_models -= len(undatable)
        added_xw -= n_before - len(tables["crosswalk"])

    schema.write_table(ORGANIZATIONS, tables["organizations"])
    schema.write_table(MODELS, list(models_by_id.values()))
    schema.write_table(EVENTS, events)
    schema.write_table(CLAIMS, flatten_claims(claims_by_event))
    schema.write_table(CROSSWALK, tables["crosswalk"])

    if review_rows:
        queue = schema.STAGING_DIR / "review_queue.csv"
        columns = ["kind", "left_source", "left_key", "right_source",
                   "right_key", "score", "note"]
        existing = []
        if queue.exists():
            with queue.open(newline="", encoding="utf-8") as fh:
                existing = list(csv.DictReader(fh))
        seen = {tuple(sorted(r.items())) for r in existing}
        merged = existing + [r for r in review_rows if tuple(sorted(r.items())) not in seen]
        with queue.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(merged)

    print(f"hf_census: swept {len(repos)} repos, {len(included)} pass inclusion, "
          f"{len(capped)} after per-org cap; +{added_models} models, "
          f"+{added_events} weights events ({outcomes.get('updated', 0)} refreshed, "
          f"{outcomes.get('skipped', 0)} curated left alone), +{added_xw} crosswalk rows, "
          f"{len(captures)} Wayback captures available, {len(review_rows)} queued for review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
