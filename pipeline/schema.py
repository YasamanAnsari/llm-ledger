"""Shared schema definitions and deterministic CSV I/O for llm-ledger.

Single source of truth for table columns, controlled vocabularies, and the
canonical on-disk representation (UTF-8, RFC 4180, LF line endings, rows
sorted by primary key). Every script reads and writes tables through the
helpers here so regeneration is byte-identical.
"""

from __future__ import annotations

import csv
import hashlib
import json
import io
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = REPO_ROOT / "data" / "core"
GENERATED_DIR = REPO_ROOT / "data" / "generated"
RAW_DIR = REPO_ROOT / "data" / "raw"
STAGING_DIR = REPO_ROOT / "data" / "staging"

# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------

ORG_TYPES = {"big_tech", "ai_lab", "startup", "academic", "government", "nonprofit"}

MODEL_TYPES = {"llm", "vlm", "multimodal", "image_gen", "video_gen", "audio", "embedding"}

VARIANT_ROLES = {
    "base", "mini", "nano", "pro", "thinking", "instruct", "chat", "coder",
    "vision", "other",
}

ACCESS_TYPES = {"open_weights", "api_only", "consumer_only", "internal", "never_released"}

LICENSE_FAMILIES = {"proprietary", "open_weights_restricted", "osi_approved"}

DERIVATIVE_TYPES = {"finetune", "distill", "quantization", "merge", "continued_pretrain"}

EVENT_TYPES = {
    "announced", "preview", "paper_published", "system_card", "api_preview",
    "api_ga", "weights_released", "consumer_rollout", "free_tier",
    "platform_availability", "price_changed", "feature_added",
    "alias_repointed", "renamed", "deprecation_announced", "retired",
}

AVAILABILITY_EVENT_TYPES = {"api_ga", "weights_released", "consumer_rollout"}
FALLBACK_AVAILABILITY_EVENT_TYPES = {"api_preview", "free_tier"}

PRECISIONS = {"day", "month", "quarter", "year"}

SOURCE_TYPES = {
    "vendor_blog", "vendor_docs", "vendor_changelog", "deprecation_page",
    "system_card", "arxiv", "hf_hub", "github", "modelscope", "api_metadata",
    "lifecycle_table", "news", "wikipedia", "community_timeline",
    "published_paper", "wayback",
}

CONFIDENCES = {"verified", "inferred", "disputed"}

# Derived per model by build.py from its events (see compute_derived):
#   human_reviewed       a named person verified at least one event
#   machine_corroborated at least one event is verified by llm-ledger
#   unreviewed           machine claims only, none corroborated
REVIEW_STATUSES = {"unreviewed", "machine_corroborated", "human_reviewed"}

CROSSWALK_NAMESPACES = {
    "openrouter", "models_dev", "huggingface", "modelscope", "openai_api",
    "anthropic_api", "google_api", "mistral_api", "epoch", "wikipedia",
    "lmarena", "text_surface_forms",
}

# HF license tags that are OSI-approved; everything else with a tag is
# open_weights_restricted.
LICENSE_OSI = {
    "apache-2.0", "mit", "bsd-3-clause", "bsd-2-clause", "cc0-1.0", "openrail",
    "gpl-3.0", "agpl-3.0", "mpl-2.0",
}

REASONING_TYPES = {"none", "always_on", "toggleable", "effort_tiered"}

REASONING_VISIBILITY = {"hidden", "summarized", "full"}

FEATURE_ADDED_DETAILS = {
    "vision", "voice", "tool_use", "long_context", "web_browsing",
    "file_upload", "structured_output",
}

MODALITIES = {"text", "image", "audio", "video", "pdf"}

BOOL_VALUES = {"true", "false"}

# Derived first_availability_via values.
FIRST_AVAILABILITY_VIA = AVAILABILITY_EVENT_TYPES | {
    "api_preview_fallback", "free_tier_fallback", "platform_availability_fallback",
}

# Epoch-owned numeric concepts that must never appear as core columns
# (validation rule 10).
EPOCH_FORBIDDEN_COLUMN_TOKENS = (
    "parameter", "compute", "flop", "dataset_size", "training_cost",
    "hardware", "training_time", "training_power",
)

# ---------------------------------------------------------------------------
# Table definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Table:
    name: str
    filename: str
    columns: tuple
    # Columns forming the primary key, in order.
    pk: tuple


ORGANIZATIONS = Table(
    name="organizations",
    filename="organizations.csv",
    columns=(
        "org_id", "canonical_name", "short_name", "aliases", "parent_org_id",
        "country", "org_type", "is_active", "epoch_org_name", "notes",
    ),
    pk=("org_id",),
)

MODELS = Table(
    name="models",
    filename="models.csv",
    columns=(
        "model_id", "canonical_name", "family", "variant_role",
        "developer_org_id", "developing_lab", "co_developer_org_ids",
        "model_type", "access_type", "license", "license_family",
        "license_has_usage_thresholds", "license_requires_separate_agreement",
        "is_derivative", "derivative_type", "base_model_id",
        "parent_model_id", "snapshot_of", "predecessor_id", "successor_id",
        "first_public_availability_date", "first_availability_via",
        "anticipation_days", "review_status", "record_created",
        "record_updated", "notes",
    ),
    pk=("model_id",),
)

EVENTS = Table(
    name="events",
    filename="events.csv",
    columns=(
        "event_id", "model_id", "event_type", "date", "precision", "region",
        "platform", "detail", "source_url", "source_type", "confidence",
        "verified_by", "verified_date", "notes",
    ),
    pk=("event_id",),
)

CROSSWALK = Table(
    name="crosswalk",
    filename="crosswalk.csv",
    columns=("model_id", "namespace", "identifier"),
    pk=("model_id", "namespace", "identifier"),
)

ATTRIBUTES = Table(
    name="attributes",
    filename="attributes.csv",
    columns=(
        "model_id", "reasoning_supported", "reasoning_type", "reasoning_effort_levels",
        "reasoning_tokens_billed", "reasoning_tokens_visible",
        "reasoning_is_separate_checkpoint", "context_length",
        "max_output_tokens", "modality_in", "modality_out",
        "knowledge_cutoff", "supports_tool_use", "supports_structured_output",
        "supports_caching", "price_input", "price_output",
        "price_cached_input", "price_date", "source_url",
    ),
    pk=("model_id",),
)

# Evidence behind machine-assessed events: one row per (event, source).
# events.csv holds the conclusion; this table holds every claim it rests
# on, so loaders re-assess from the full set each run and researchers can
# see exactly which sources said what.
CLAIMS = Table(
    name="claims",
    filename="claims.csv",
    columns=("event_id", "source_url", "source_type", "date", "precision",
             "label", "bound", "first_party"),
    pk=("event_id", "source_url"),
)

CORE_TABLES = (ORGANIZATIONS, MODELS, EVENTS, CLAIMS, CROSSWALK, ATTRIBUTES)
TABLES_BY_NAME = {t.name: t for t in CORE_TABLES}

# ---------------------------------------------------------------------------
# Deterministic CSV I/O
# ---------------------------------------------------------------------------


def read_table(table: Table, directory: Path = CORE_DIR) -> list:
    """Read a core table as a list of dicts (all values are strings)."""
    path = directory / table.filename
    if not path.exists():
        raise FileNotFoundError(f"required table missing: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = tuple(reader.fieldnames or ())
        if header != table.columns:
            raise ValueError(
                f"{path} header mismatch.\n expected: {table.columns}\n found:    {header}"
            )
        return [dict(row) for row in reader]


def rows_to_csv_bytes(table: Table, rows: list) -> bytes:
    """Serialize rows deterministically: PK-sorted, LF, minimal quoting."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=table.columns, lineterminator="\n")
    writer.writeheader()
    for row in sorted(rows, key=lambda r: tuple(r.get(c, "") for c in table.pk)):
        unknown = set(row) - set(table.columns)
        if unknown:
            raise ValueError(f"{table.name}: unknown columns {sorted(unknown)}")
        writer.writerow({c: row.get(c, "") for c in table.columns})
    return buf.getvalue().encode("utf-8")


def write_table(table: Table, rows: list, directory: Path = CORE_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / table.filename
    path.write_bytes(rows_to_csv_bytes(table, rows))
    return path


def load_core() -> dict:
    """Load all core tables keyed by table name."""
    return {t.name: read_table(t) for t in CORE_TABLES}


# ---------------------------------------------------------------------------
# Raw snapshot helpers (Tier-1 pulls)
# ---------------------------------------------------------------------------


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def snapshot_dir(source: str, day: str = "") -> Path:
    d = RAW_DIR / source / (day or today_utc())
    d.mkdir(parents=True, exist_ok=True)
    return d


def latest_snapshot_dir(source: str) -> Path:
    """Most recent dated snapshot directory for a source; raises if none."""
    base = RAW_DIR / source
    if not base.exists():
        raise FileNotFoundError(f"no snapshots for source '{source}' under {base}")
    dirs = sorted(p for p in base.iterdir() if p.is_dir())
    if not dirs:
        raise FileNotFoundError(f"no dated snapshot directories under {base}")
    return dirs[-1]


def write_snapshot(source: str, filename: str, payload: bytes, url: str) -> Path:
    """Store a raw payload plus a committed manifest (URL + hash, no payload)."""
    d = snapshot_dir(source)
    path = d / filename
    path.write_bytes(payload)
    manifest_path = d / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[filename] = {
        "url": url,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def date_matches_precision(value: str, precision: str) -> bool:
    """Rule 3: stored date must sit on the first day of its stated period."""
    try:
        d = parse_iso_date(value)
    except ValueError:
        return False
    if precision == "day":
        return True
    if precision == "month":
        return d.day == 1
    if precision == "quarter":
        return d.day == 1 and d.month in (1, 4, 7, 10)
    if precision == "year":
        return d.day == 1 and d.month == 1
    return False


def derivative_from_name(model_id: str) -> str:
    """Derivative type a model name states outright, else "".

    Only markers that are unambiguous in lab naming are automated:
    `distill` (DeepSeek-R1-Distill-*) and `merge`. Fine-tunes are a human
    call: `-instruct` / `-sft` checkpoints are usually a lab's own release.
    """
    tokens = set(model_id.lower().split("-"))
    if "distill" in tokens or "distilled" in tokens:
        return "distill"
    if "merge" in tokens or "merged" in tokens:
        return "merge"
    return ""


def license_family(license_tag: str) -> str:
    if not license_tag:
        return ""
    return "osi_approved" if license_tag.lower() in LICENSE_OSI else "open_weights_restricted"


def next_event_id(existing_events: list, model_id: str, event_type: str) -> str:
    """Allocate `{model_id}-{event_type}-{seq}` continuing from existing rows."""
    prefix = f"{model_id}-{event_type}-"
    seqs = [
        int(e["event_id"][len(prefix):])
        for e in existing_events
        if e["event_id"].startswith(prefix) and e["event_id"][len(prefix):].isdigit()
    ]
    return f"{prefix}{max(seqs, default=0) + 1}"
