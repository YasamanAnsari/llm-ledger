"""Name normalization and cross-source matching (crosswalk builder).

Joins the latest models.dev, OpenRouter, and Epoch snapshots on normalized
model names. Exact/variant matches join directly; fuzzy candidates are
auto-accepted at rapidfuzz ratio >= 97, queued for manual review in the
92-97 band, and discarded below 92 (a poisoned crosswalk is worse than a
missing match).

Outputs:
    data/generated/matched_models.csv   one row per matched cluster
    data/staging/review_queue.csv       fuzzy candidates awaiting a human
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

from rapidfuzz import fuzz, process

sys.path.insert(0, str(Path(__file__).resolve().parent))

import schema

AUTO_ACCEPT = 97.0
QUEUE_FLOOR = 92.0

MATCHED_COLUMNS = [
    "match_key", "sources", "match_method", "vendor_prefix",
    "or_prefix", "md_prefix",
    "md_provider", "md_model_key", "md_release_date", "md_provider_count",
    "md_open_weights", "md_modalities_in", "md_modalities_out",
    "md_context_length", "md_cost_input", "md_cost_output", "md_reasoning",
    "or_id", "or_created", "or_expiration",
    "epoch_model", "epoch_organization", "epoch_publication_date",
    "epoch_confidence",
]

# Leading org tokens that are naming noise, not family names.
PREFIX_REWRITES = (
    ("meta-llama-", "llama-"),
    ("deepseek-ai-", "deepseek-"),
    ("moonshotai-", "kimi-"),
    ("google-", ""),
    ("openai-", ""),
    ("anthropic-", ""),
    ("mistralai-", ""),
    ("z-ai-", ""),
    ("zhipu-", ""),
    ("01-ai-", ""),
    ("xai-", ""),
)

# Trailing tokens that distinguish serving format, not checkpoint identity.
STRIP_SUFFIXES = ("-instruct", "-chat", "-it", "-hf")

# Date-like suffixes marking a dated snapshot of an alias.
DATE_SUFFIX_RE = re.compile(r"-(20\d{2}-?\d{2}-?\d{2}|20\d{6})$")
MMDD_SUFFIX_RE = re.compile(r"-(0[1-9]|1[0-2])([0-2]\d|3[01])$")


def normalize_name(raw: str) -> dict:
    """Normalize a model identifier to a match key.

    Returns {key, prefix, snapshot_suffix}: the vendor prefix (before '/')
    and any date suffix are preserved as metadata, since a date suffix marks
    a dated snapshot candidate rather than a distinct model family member.
    """
    text = raw.strip().lower()
    prefix = ""
    if "/" in text:
        prefix, text = text.split("/", 1)
    text = text.split(":", 1)[0]  # OpenRouter serving variants (:free, :batch)
    text = re.sub(r"[\s_.()\[\]]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")

    snapshot_suffix = ""
    m = DATE_SUFFIX_RE.search(text) or MMDD_SUFFIX_RE.search(text)
    if m:
        snapshot_suffix = m.group(0).lstrip("-")
        text = text[: m.start()]

    for old, new in PREFIX_REWRITES:
        if text.startswith(old):
            text = new + text[len(old):]
            break
    return {"key": text, "prefix": prefix, "snapshot_suffix": snapshot_suffix}


def slug_for(key: str, org_id: str) -> str:
    """Ledger model_id for a normalized key.

    Very short keys (o3, r1, hy3...) get the org prefix, mirroring spec
    examples like `openai-o3`; longer keys are already self-identifying.
    Shared by reconcile and the HF census so both derive the same id.
    """
    if len(key) <= 4 and org_id and not key.startswith(org_id):
        return f"{org_id}-{key}"
    return key


def key_variants(key: str) -> list:
    """Match key plus serving-format-stripped variants, most specific first.

    Also bridges the letter-digit boundary spelling split: vendors write
    "Qwen2.5-72B" (fused) while aggregators write "qwen-2.5-72b" (split),
    which normalize to different keys (qwen2-5-... vs qwen-2-5-...).
    """
    variants = [key]
    fused = re.sub(r"^([a-z]+)-(\d)", r"\1\2", key)
    split = re.sub(r"^([a-z]+)(\d)", r"\1-\2", key)
    for alt in (fused, split):
        if alt != key:
            variants.append(alt)
    for suffix in STRIP_SUFFIXES:
        if key.endswith(suffix):
            variants.append(key[: -len(suffix)])
            for alt in (fused, split):
                if alt != key and alt.endswith(suffix):
                    variants.append(alt[: -len(suffix)])
    return variants


def _read_normalized(source: str) -> list:
    path = schema.latest_snapshot_dir(source) / "normalized.csv"
    if not path.exists():
        raise FileNotFoundError(f"run the {source} puller first: {path} missing")
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_models_dev() -> dict:
    """Normalized key -> aggregated models.dev record.

    models.dev lists the same model under many reseller providers, all
    claiming the model's release date. We keep the most common claimed date
    (resellers occasionally carry Jan-1 placeholders; the mode across
    providers is the curated value), count distinct providers, and prefer
    the record whose provider matches the vendor prefix embedded in the
    model key (first-party metadata).
    """
    grouped: dict = {}
    for row in _read_normalized("models_dev"):
        norm = normalize_name(row["model_key"])
        if not norm["key"]:
            continue
        entry = grouped.setdefault(norm["key"], {"rows": [], "providers": set()})
        entry["rows"].append((norm, row))
        entry["providers"].add(row["provider"])

    result = {}
    for key, entry in grouped.items():
        dated = [(n, r) for n, r in entry["rows"] if r["release_date"]]
        pool = dated or entry["rows"]
        first_party = [
            (n, r) for n, r in pool
            if n["prefix"] and n["prefix"] in r["provider"]
        ] or pool
        norm, best = min(first_party, key=lambda item: item[1]["release_date"] or "9999")
        date_counts = Counter(r["release_date"] for _, r in dated)
        # Most common claim wins; ties break toward the earlier date.
        mode_date = min(
            (d for d, n in date_counts.items() if n == max(date_counts.values())),
            default="",
        )
        result[key] = {
            "norm": norm,
            "row": best,
            "release_date": mode_date,
            "provider_count": len(entry["providers"]),
        }
    return result


def load_openrouter() -> dict:
    """Normalized key -> earliest-created OpenRouter record."""
    result: dict = {}
    for row in _read_normalized("openrouter"):
        norm = normalize_name(row["id"])
        key = norm["key"]
        if not key:
            continue
        if key not in result or (row["created_date"] or "9999") < (result[key]["row"]["created_date"] or "9999"):
            result[key] = {"norm": norm, "row": row}
    return result


def load_epoch() -> dict:
    result: dict = {}
    for row in _read_normalized("epoch"):
        norm = normalize_name(row["model"])
        key = norm["key"]
        if key and key not in result:
            result[key] = {"norm": norm, "row": row}
    return result


def _variant_index(records: dict) -> dict:
    """variant key -> canonical key, most specific variant wins."""
    index = {}
    for key in records:
        for variant in key_variants(key):
            index.setdefault(variant, key)
    return index


def _fuzzy_pairs(left_keys: list, right_index: dict) -> list:
    """(left_key, right_key, score) for best fuzzy candidates >= QUEUE_FLOOR."""
    choices = list(right_index)
    pairs = []
    for key in left_keys:
        found = process.extractOne(
            key, choices, scorer=fuzz.ratio, score_cutoff=QUEUE_FLOOR
        )
        if found:
            pairs.append((key, right_index[found[0]], found[1]))
    return pairs


def match() -> tuple:
    """Returns (matched_rows, review_queue_rows)."""
    md = load_models_dev()
    orr = load_openrouter()
    epoch = load_epoch()

    md_index = _variant_index(md)
    epoch_index = _variant_index(epoch)

    # cluster key (models.dev key when present) -> {"md":, "or":, "epoch":, "method":}
    clusters: dict = {}
    review_queue: list = []

    def cluster_for(key: str) -> dict:
        return clusters.setdefault(key, {"md": None, "or": None, "epoch": None, "methods": []})

    for key, record in md.items():
        cluster_for(key)["md"] = record

    # --- OpenRouter -> models.dev ---
    unmatched_or = []
    for key, record in orr.items():
        hit = next((md_index[v] for v in key_variants(key) if v in md_index), None)
        if hit:
            c = cluster_for(hit)
            c["or"] = record
            c["methods"].append("or:exact")
        else:
            unmatched_or.append(key)
    for left, right, score in _fuzzy_pairs(unmatched_or, md_index):
        if score >= AUTO_ACCEPT:
            c = cluster_for(right)
            c["or"] = orr[left]
            c["methods"].append(f"or:fuzzy:{score:.0f}")
        else:
            review_queue.append({
                "kind": "fuzzy_match", "left_source": "openrouter",
                "left_key": left, "right_source": "models_dev",
                "right_key": right, "score": f"{score:.1f}",
                "note": "92-97 band: confirm or reject before crosswalking",
            })
    matched_or = {id(c["or"]) for c in clusters.values() if c["or"]}
    for key, record in orr.items():
        if id(record) not in matched_or and key not in clusters:
            clusters[key] = {"md": None, "or": record, "epoch": None, "methods": ["or:only"]}

    # --- Epoch -> clusters (models.dev keys, then OpenRouter-only keys) ---
    cluster_index = _variant_index(clusters)
    unmatched_epoch = []
    for key, record in epoch.items():
        hit = next((cluster_index[v] for v in key_variants(key) if v in cluster_index), None)
        if hit:
            c = clusters[hit]
            c["epoch"] = record
            c["methods"].append("epoch:exact")
        else:
            unmatched_epoch.append(key)
    for left, right, score in _fuzzy_pairs(unmatched_epoch, cluster_index):
        if score >= AUTO_ACCEPT:
            c = clusters[right]
            if c["epoch"] is None:
                c["epoch"] = epoch[left]
                c["methods"].append(f"epoch:fuzzy:{score:.0f}")
        else:
            review_queue.append({
                "kind": "fuzzy_match", "left_source": "epoch",
                "left_key": left, "right_source": "ledger_cluster",
                "right_key": right, "score": f"{score:.1f}",
                "note": "92-97 band: confirm or reject before crosswalking",
            })

    rows = []
    for key in sorted(clusters):
        c = clusters[key]
        sources = [s for s, present in
                   (("models_dev", c["md"]), ("openrouter", c["or"]), ("epoch", c["epoch"]))
                   if present]
        md_rec, or_rec, ep_rec = c["md"], c["or"], c["epoch"]
        prefix = ""
        # OpenRouter's vendor namespace is curated (true developer); models.dev
        # keys often carry a hosting-provider or base-family prefix instead.
        for rec in (or_rec, md_rec):
            if rec and rec["norm"]["prefix"]:
                prefix = rec["norm"]["prefix"]
                break
        rows.append({
            "match_key": key,
            "sources": "|".join(sources),
            "match_method": "|".join(sorted(set(c["methods"]))) or "md:only",
            "vendor_prefix": prefix,
            "or_prefix": or_rec["norm"]["prefix"] if or_rec else "",
            "md_prefix": md_rec["norm"]["prefix"] if md_rec else "",
            "md_provider": md_rec["row"]["provider"] if md_rec else "",
            "md_model_key": md_rec["row"]["model_key"] if md_rec else "",
            "md_release_date": md_rec["release_date"] if md_rec else "",
            "md_provider_count": md_rec["provider_count"] if md_rec else "",
            "md_open_weights": md_rec["row"]["open_weights"] if md_rec else "",
            "md_modalities_in": md_rec["row"]["modalities_in"] if md_rec else "",
            "md_modalities_out": md_rec["row"]["modalities_out"] if md_rec else "",
            "md_context_length": md_rec["row"]["context_length"] if md_rec else "",
            "md_cost_input": md_rec["row"]["cost_input"] if md_rec else "",
            "md_cost_output": md_rec["row"]["cost_output"] if md_rec else "",
            "md_reasoning": md_rec["row"]["reasoning"] if md_rec else "",
            "or_id": or_rec["row"]["id"] if or_rec else "",
            "or_created": or_rec["row"]["created_date"] if or_rec else "",
            "or_expiration": or_rec["row"]["expiration_date"] if or_rec else "",
            "epoch_model": ep_rec["row"]["model"] if ep_rec else "",
            "epoch_organization": ep_rec["row"]["organization"] if ep_rec else "",
            "epoch_publication_date": ep_rec["row"]["publication_date"] if ep_rec else "",
            "epoch_confidence": ep_rec["row"]["confidence"] if ep_rec else "",
        })
    return rows, review_queue


def main() -> int:
    rows, review_queue = match()

    out = schema.GENERATED_DIR / "matched_models.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MATCHED_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    schema.STAGING_DIR.mkdir(parents=True, exist_ok=True)
    queue_path = schema.STAGING_DIR / "review_queue.csv"
    queue_columns = ["kind", "left_source", "left_key", "right_source",
                     "right_key", "score", "note"]
    # The queue is shared: this script owns only kind=fuzzy_match rows and
    # must preserve rows appended by other pullers (hf_census, pull_nhlocal).
    foreign_rows = []
    if queue_path.exists():
        with queue_path.open(newline="", encoding="utf-8") as fh:
            foreign_rows = [r for r in csv.DictReader(fh) if r["kind"] != "fuzzy_match"]
    with queue_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=queue_columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(review_queue, key=lambda r: (r["left_source"], r["left_key"])))
        writer.writerows(foreign_rows)

    multi = sum(1 for r in rows if "|" in r["sources"])
    print(f"match: {len(rows)} clusters, {multi} matched across >=2 sources, "
          f"{len(review_queue)} in review queue -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
