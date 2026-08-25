"""Apply the inclusion rule to the HF snapshot and load the open-weight census.

Inclusion rule: a model enters the ledger if it is a distinct trained
checkpoint from an organization, released under its own name. Quantizations,
format conversions, LoRA adapters, and community merges are excluded unless
independently notable.

For each included repo:
- reuses an existing models row when the normalized name matches (adding the
  huggingface crosswalk id and a weights_released event if missing),
- otherwise drafts a new models row,
- adds a `weights_released` event dated from repo `createdAt`, which is a
  primary machine source -> confidence=verified, verified_by=llm-ledger.
  The 2022-03-02 HF backfill artifact is queued for review, never used.
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
from schema import CROSSWALK, EVENTS, MODELS, ORGANIZATIONS

HF_BACKFILL_DATE = "2022-03-02"

# Conversion/adapter markers: these repos repackage an existing checkpoint.
EXCLUDE_NAME_RE = re.compile(
    r"(gguf|awq|gptq|exl2|onnx|openvino|mlx|-mxfp4|-nvfp4|w4a16|w8a8|"
    r"-4bit|-8bit|-fp4|-bnb|bitsandbytes|-lora|-adapter|-dpo-lora)",
    re.IGNORECASE,
)
EXCLUDE_TAGS = {"gguf", "awq", "gptq", "onnx", "mlx", "peft", "lora", "adapter"}

PER_ORG_CAP = 40  # top downloads per org; long-tail checkpoints add noise

LICENSE_OSI = {
    "apache-2.0", "mit", "bsd-3-clause", "bsd-2-clause", "cc0-1.0", "openrail",
    "gpl-3.0", "agpl-3.0", "mpl-2.0",
}


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


def license_family(license_tag: str) -> str:
    if not license_tag:
        return ""
    if license_tag.lower() in LICENSE_OSI:
        return "osi_approved"
    return "open_weights_restricted"


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
    has_weights_event = {e["model_id"] for e in events if e["event_type"] == "weights_released"}

    review_rows = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = date.today().isoformat()

    included = [r for r in repos if include(r)]
    by_org: dict = {}
    for row in included:
        by_org.setdefault(row["org_id"], []).append(row)
    capped = []
    for org, rows in sorted(by_org.items()):
        rows.sort(key=lambda r: -int(r["downloads"] or 0))
        capped.extend(rows[:PER_ORG_CAP])

    added_models = added_events = added_xw = 0
    drafted_this_run: set = set()
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
            is_distill = "distill" in model_id
            models_by_id[model_id] = {
                "model_id": model_id,
                "canonical_name": name,
                "variant_role": "other",
                "developer_org_id": row["org_id"],
                "model_type": "vlm" if row["pipeline_tag"] == "image-text-to-text" else "llm",
                "access_type": "open_weights",
                "license": row["license"],
                "license_family": license_family(row["license"]),
                "is_derivative": "true" if is_distill else "false",
                "derivative_type": "distill" if is_distill else "",
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

        if model_id in has_weights_event or not row["created_at"]:
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
        events.append({
            "event_id": schema.next_event_id(events, model_id, "weights_released"),
            "model_id": model_id,
            "event_type": "weights_released",
            "date": row["created_at"],
            "precision": "day",
            "region": "global",
            "source_url": f"https://huggingface.co/{repo_id}",
            "source_type": "hf_hub",
            "confidence": "verified",
            "verified_by": "llm-ledger",
            "verified_date": today,
            "notes": "repo creation timestamp from the Hub API (primary machine source)",
        })
        has_weights_event.add(model_id)
        added_events += 1

    # A drafted model that ended up with no datable event would violate
    # validation rule 6 (>= 1 event per model): withdraw it and keep only the
    # review-queue lead. Its date needs a human-found primary source first.
    undatable = {m for m in drafted_this_run if m not in has_weights_event}
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
          f"+{added_events} weights events, +{added_xw} crosswalk rows, "
          f"{len(review_rows)} queued for review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
