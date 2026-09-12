"""Build derived fields and generated artifacts for llm-ledger.

- Recomputes the derived columns on models.csv in place.
- Generates data/generated/llm_ledger_wide.csv (one row per model, event
  types pivoted to `{event_type}_date` / `{event_type}_precision`, global
  region only, joined with models + attributes).
- Generates data/generated/llm_ledger_enriched.csv (wide LEFT JOINed to the
  latest Epoch snapshot via the crosswalk; Epoch is CC-BY and credited).
- Generates data/generated/models_latest.csv, a reading view of models.csv:
  the identifying columns with first_public_availability_date first, newest
  releases at the top, undated models last.
- Generates the coverage and treatment-date sensitivity reports and the
  README stats block, so no number in the repository can go stale.
- Generates data/generated/reschedules.csv: every time a source moved its
  date for an event (from claims.csv's superseded rows), signed in days.
- Fills `family` and `variant_role` from the model name where no curator
  has set them (schema.family_and_role).

Everything here is deterministic: fixed column orders, PK-sorted rows, no
run timestamps in output, snapshot dates taken from payload content rather
than pull day. `validate.py` rule 9 rebuilds every artifact in
GENERATED_ARTIFACTS (plus the README) in memory and byte-compares it
against the file on disk.
"""

from __future__ import annotations

import csv
import io
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import schema
import sensitivity
from confidence import PROJECT_VERIFIERS, curated_model_ids, is_machine_row, live_claims
from schema import (
    ATTRIBUTES, AVAILABILITY_EVENT_TYPES, EVENTS,
    FALLBACK_AVAILABILITY_EVENT_TYPES, GENERATED_DIR, MODELS,
)

# Tie priority for first_availability_via.
VIA_PRIORITY = ("weights_released", "api_ga", "consumer_rollout")
FALLBACK_VIA_PRIORITY = ("api_preview", "free_tier", "platform_availability")

# Stable pivot order for the wide file.
WIDE_EVENT_ORDER = (
    "announced", "preview", "paper_published", "system_card", "api_preview",
    "api_ga", "weights_released", "consumer_rollout", "free_tier",
    "platform_availability", "price_changed", "feature_added",
    "alias_repointed", "renamed", "deprecation_announced", "retired",
)

# Epoch columns worth carrying into the enriched file, matched by substring
# against the snapshot header (Epoch occasionally renames columns).
EPOCH_CARRY_TOKENS = (
    "publication date", "parameters", "training compute", "dataset size",
    "training cost", "compute cost", "confidence", "model accessibility",
    "country", "link",
)


# Only dates precise to the day or month may become "the" availability date.
# A catalog's Jan-1 placeholder is a year, not a launch day.
HEADLINE_PRECISIONS = {"day", "month"}


def _earliest_global(events: list, model_id: str, event_types: set,
                     precisions: set | None = None) -> list:
    """Global-region events of the given types for one model, date-sorted;
    optionally restricted to the given precisions."""
    rows = [
        e for e in events
        if e["model_id"] == model_id
        and e.get("region", "global") == "global"
        and e["event_type"] in event_types
        and e.get("date")
        and (precisions is None or e.get("precision") in precisions)
    ]
    return sorted(rows, key=lambda e: e["date"])


def _pick_first(rows: list, priority: tuple) -> dict:
    """Earliest row; ties on date broken by the spec's event-type priority."""
    best_date = rows[0]["date"]
    tied = [r for r in rows if r["date"] == best_date]
    tied.sort(key=lambda r: priority.index(r["event_type"]))
    return tied[0]


def compute_derived(models: list, events: list) -> list:
    """Return models rows with spec-section-5 derived columns recomputed."""
    out, derived_family = [], []
    curated_ids = curated_model_ids(events)
    for row in models:
        row = dict(row)
        mid = row["model_id"]
        first_date, via, via_precision, via_confidence = "", "", "", ""

        primary = _earliest_global(events, mid, AVAILABILITY_EVENT_TYPES, HEADLINE_PRECISIONS)
        if primary:
            chosen = _pick_first(primary, VIA_PRIORITY)
            first_date, via = chosen["date"], chosen["event_type"]
            via_precision, via_confidence = chosen["precision"], chosen.get("confidence", "")
        else:
            # Third tier: a third-party platform listing is an upper bound on
            # public availability, better than no date at all.
            fallback = (_earliest_global(events, mid, FALLBACK_AVAILABILITY_EVENT_TYPES,
                                         HEADLINE_PRECISIONS)
                        or _earliest_global(events, mid, {"platform_availability"},
                                            HEADLINE_PRECISIONS))
            if fallback:
                chosen = _pick_first(fallback, FALLBACK_VIA_PRIORITY)
                first_date, via = chosen["date"], chosen["event_type"] + "_fallback"
                via_precision, via_confidence = chosen["precision"], chosen.get("confidence", "")

        row["first_public_availability_date"] = first_date
        row["first_availability_via"] = via
        row["first_availability_confidence"] = via_confidence

        anticipation = ""
        announced = _earliest_global(events, mid, {"announced"})
        if announced and first_date:
            ann = announced[0]
            precisions_ok = {ann["precision"], via_precision} <= {"day", "month"}
            if precisions_ok:
                delta = (date.fromisoformat(first_date)
                         - date.fromisoformat(ann["date"])).days
                anticipation = str(delta)
        row["anticipation_days"] = anticipation
        curated = mid in curated_ids
        # A machine-drafted row whose weights turned up on the Hub is open
        # weight whatever a reseller flag said; curated rows are a human call.
        if (not curated and row.get("access_type") == "api_only"
                and _earliest_global(events, mid, {"weights_released"})):
            row["access_type"] = "open_weights"

        # family / variant_role come from the name unless a person reviewed
        # the model, in which case the curated values stand and only blanks
        # are filled. Recomputing (rather than filling once) means a better
        # parser reaches every machine row on the next build.
        family, role = schema.family_and_role(row.get("canonical_name") or mid)
        if not (curated and row.get("family")):
            row["family"] = family
            derived_family.append(row)
        if not (curated and row.get("variant_role")):
            row["variant_role"] = role
        out.append(row)

    # Catalogs spell the same family differently ("Qwen3" / "qwen3"); the
    # most common spelling wins for name-derived values, and a curated
    # spelling beats any number of catalog ones.
    derived_ids = {id(r) for r in derived_family}
    spellings: dict = {}
    for row in out:
        if row["family"]:
            weight = 1 if id(row) in derived_ids else len(out)
            spellings.setdefault(row["family"].lower(), Counter())[row["family"]] += weight
    for row in derived_family:
        if row["family"]:
            row["family"] = spellings[row["family"].lower()].most_common(1)[0][0]
    return out


def _wide_columns(attr_columns: tuple) -> list:
    cols = list(MODELS.columns)
    for et in WIDE_EVENT_ORDER:
        cols += [f"{et}_date", f"{et}_precision"]
    cols += [c for c in attr_columns if c != "model_id"]
    return cols


def build_wide_rows() -> tuple:
    """(columns, rows) for the wide artifact, computed from core tables."""
    models = schema.read_table(MODELS)
    events = schema.read_table(EVENTS)
    attributes = {r["model_id"]: r for r in schema.read_table(ATTRIBUTES)}

    models = compute_derived(models, events)
    columns = _wide_columns(ATTRIBUTES.columns)

    rows = []
    for m in sorted(models, key=lambda r: r["model_id"]):
        row = dict(m)
        for et in WIDE_EVENT_ORDER:
            # Repeatable event types (price_changed, platform_availability,
            # ...) pivot to their EARLIEST global occurrence; full history
            # stays in events.csv.
            found = _earliest_global(events, m["model_id"], {et})
            row[f"{et}_date"] = found[0]["date"] if found else ""
            row[f"{et}_precision"] = found[0]["precision"] if found else ""
        attr = attributes.get(m["model_id"], {})
        for c in ATTRIBUTES.columns:
            if c != "model_id":
                row[c] = attr.get(c, "")
        rows.append(row)
    return columns, rows


def _csv_bytes(columns: list, rows: list) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buf.getvalue().encode("utf-8")


def build_wide_bytes() -> bytes:
    columns, rows = build_wide_rows()
    return _csv_bytes(columns, rows)


LATEST_DATE_COLUMN = "first_public_availability_date"
# A reading view: what someone scanning "what came out" wants to see. The
# sparse curated columns (license flags, lineage) stay in models.csv.
LATEST_COLUMNS = (
    LATEST_DATE_COLUMN, "first_availability_via", "first_availability_confidence",
    "model_id", "canonical_name",
    "developer_org_id", "family", "variant_role", "model_type", "access_type",
    "license_family",
)


def latest_first(models: list) -> list:
    """models rows newest-first by availability date; undated rows last;
    model_id (ascending) breaks ties. Rows are returned unchanged."""
    rows = sorted(models, key=lambda r: r["model_id"])
    # Stable reverse sort keeps the model_id order within a date; "" (undated)
    # is the smallest ISO string so it lands at the bottom.
    rows.sort(key=lambda r: r[LATEST_DATE_COLUMN], reverse=True)
    return rows


def build_latest_bytes() -> bytes:
    models = compute_derived(schema.read_table(MODELS), schema.read_table(EVENTS))
    return _csv_bytes(list(LATEST_COLUMNS), latest_first(models))


# ---------------------------------------------------------------------------
# Enriched artifact (Epoch LEFT JOIN, CC-BY with credit)
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _load_epoch_snapshot() -> tuple:
    """(content_date, header, rows_by_model_name) from the latest raw pull.

    The date is when this payload first appeared, so an unchanged Epoch
    file does not rewrite `epoch_snapshot_date` on every row each day."""
    csv_path = schema.snapshot_file("epoch", "all_ai_models.csv")
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        by_name = {}
        for row in reader:
            name = (row.get("Model") or row.get("System") or "").strip()
            if name and name not in by_name:
                by_name[name] = row
    return schema.snapshot_content_date("epoch", "all_ai_models.csv"), header, by_name


def build_enriched_bytes() -> bytes:
    wide_columns, wide_rows = build_wide_rows()
    snapshot_date, epoch_header, epoch_by_name = _load_epoch_snapshot()

    carry = [
        col for col in epoch_header
        if any(token in col.lower() for token in EPOCH_CARRY_TOKENS)
    ]
    epoch_columns = [f"epoch_{_slug(col)}" for col in carry]

    crosswalk = schema.read_table(schema.CROSSWALK)
    epoch_id_by_model = {
        r["model_id"]: r["identifier"]
        for r in crosswalk if r["namespace"] == "epoch"
    }

    columns = wide_columns + epoch_columns + ["epoch_snapshot_date"]
    rows = []
    for row in wide_rows:
        row = dict(row)
        epoch_row = epoch_by_name.get(epoch_id_by_model.get(row["model_id"], ""), {})
        for src_col, dst_col in zip(carry, epoch_columns):
            row[dst_col] = epoch_row.get(src_col, "")
        row["epoch_snapshot_date"] = snapshot_date
        rows.append(row)
    return _csv_bytes(columns, rows)


README_STATS_START = "<!-- stats:start -->"
README_STATS_END = "<!-- stats:end -->"


def build_readme_stats(models: list, events: list, claims: list, organizations: list) -> str:
    """The README's headline paragraph, computed so it can never go stale."""
    n = len(models)
    conf = Counter(e["confidence"] for e in events)
    verified = [e for e in events if e["confidence"] == "verified"]
    platform_own = sum(1 for e in verified if e["event_type"] == "platform_availability")
    by_person = sum(1 for e in verified
                    if e["verified_by"] not in PROJECT_VERIFIERS and not is_machine_row(e))
    curated = len(curated_model_ids(events))
    corroborated = len({e["model_id"] for e in verified}) - curated
    cn = {o["org_id"] for o in organizations if o["country"] == "CN"}
    open_w = [m for m in models if m["access_type"] == "open_weights"]
    dated = sorted(m["first_public_availability_date"] for m in models
                   if m["first_public_availability_date"])

    def pct(part: int, whole: int) -> str:
        return f"{100 * part / whole:.0f}%" if whole else "0%"

    return "\n".join([
        f"Exact counts as of the last rebuild: {n} models from "
        f"{len({m['developer_org_id'] for m in models})} organizations, {len(events)} dated "
        f"events, backed by {len(live_claims(claims))} live source claims. First availability runs from "
        f"{dated[0]} to {dated[-1]}. {pct(len(open_w), n)} of the models are open-weight; "
        f"Chinese labs make up {pct(sum(m['developer_org_id'] in cn for m in open_w), len(open_w))} "
        f"of those.",
        "",
        f"Read the counts honestly. {pct(conf['verified'], len(events))} of events are "
        f"`verified` (two independent sources agreed within two days, or a platform reported "
        f"its own listing); {pct(platform_own, len(verified))} of those are a platform's own "
        f"listing timestamp, and {by_person} were checked by a named person. Per model: "
        f"{pct(curated, n)} have a verified event read from a primary page such as a vendor "
        f"blog or deprecation table, {pct(corroborated, n)} have only machine-corroborated "
        f"events, and the remaining {pct(n - curated - corroborated, n)} rest on a single "
        f"source. Filter on `events.confidence` before treating a date as settled.",
    ])


def render_readme(text: str, stats: str) -> str:
    """Replace whatever sits between the README stats markers."""
    start = text.index(README_STATS_START) + len(README_STATS_START)
    end = text.index(README_STATS_END)
    return text[:start] + "\n" + stats + "\n" + text[end:]


def build_readme_bytes() -> bytes:
    readme = schema.REPO_ROOT / "README.md"
    stats = build_readme_stats(
        compute_derived(schema.read_table(MODELS), schema.read_table(EVENTS)),
        schema.read_table(EVENTS), schema.read_table(schema.CLAIMS),
        schema.read_table(schema.ORGANIZATIONS))
    return render_readme(readme.read_text(encoding="utf-8"), stats).encode("utf-8")


def build_coverage_report(models: list, events: list, organizations: list) -> str:
    """Per-organization coverage and confidence, so nobody reads the row
    count as the number of checked dates."""
    org_name = {o["org_id"]: o["short_name"] or o["canonical_name"] for o in organizations}
    by_org: dict = {}
    for m in models:
        by_org.setdefault(m["developer_org_id"], []).append(m)
    events_by_model: dict = {}
    for e in events:
        events_by_model.setdefault(e["model_id"], []).append(e)

    def pct(part: int, whole: int) -> str:
        return f"{100 * part / whole:.0f}%" if whole else "-"

    curated = curated_model_ids(events)
    corroborated = {e["model_id"] for e in events if e["confidence"] == "verified"} - curated
    lines = [
        "# Coverage report",
        "",
        "Generated by `pipeline/build.py` from the core tables. A model is",
        "`curated` when at least one of its verified events was read from a",
        "primary page (vendor blog, deprecation table, arXiv), `corroborated` when",
        "its only verified events are machine rows (two independent sources agreed",
        "or a platform reported its own event), and `single-source` when no event",
        "reached `verified`. Filter on `events.confidence` before treating a date",
        "as settled.",
        "",
        f"- Models: {len(models)}; events: {len(events)}",
        f"- Models: curated {len(curated)}, corroborated {len(corroborated)}, "
        f"single-source {len(models) - len(curated) - len(corroborated)}",
        "- Event confidence: " + ", ".join(
            f"{c} {sum(1 for e in events if e['confidence'] == c)}"
            for c in ("verified", "inferred", "disputed")),
        "",
        "## By organization",
        "",
        "| org | models | events | curated | corroborated | single-source | events verified |",
        "|---|---|---|---|---|---|---|",
    ]
    for org_id, rows in sorted(by_org.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        evs = [e for m in rows for e in events_by_model.get(m["model_id"], [])]
        ids = {m["model_id"] for m in rows}
        n_curated, n_corroborated = len(ids & curated), len(ids & corroborated)
        verified = sum(1 for e in evs if e["confidence"] == "verified")
        lines.append(
            f"| {org_name.get(org_id, org_id)} | {len(rows)} | {len(evs)} | "
            f"{n_curated} | {n_corroborated} | {len(rows) - n_curated - n_corroborated} | "
            f"{pct(verified, len(evs))} |")

    lines += ["", "## By event type", "", "| event_type | rows | verified | inferred | disputed |",
              "|---|---|---|---|---|"]
    types = sorted({e["event_type"] for e in events},
                   key=lambda t: (-sum(1 for e in events if e["event_type"] == t), t))
    for t in types:
        rows = [e for e in events if e["event_type"] == t]
        lines.append(f"| {t} | {len(rows)} | "
                     + " | ".join(str(sum(1 for e in rows if e["confidence"] == c))
                                  for c in ("verified", "inferred", "disputed")) + " |")
    return "\n".join(lines) + "\n"


def build_coverage_bytes() -> bytes:
    models = compute_derived(schema.read_table(MODELS), schema.read_table(EVENTS))
    return build_coverage_report(models, schema.read_table(EVENTS),
                                 schema.read_table(schema.ORGANIZATIONS)).encode("utf-8")


def build_sensitivity_bytes() -> bytes:
    models = {m["model_id"]: m for m in schema.read_table(MODELS)}
    return sensitivity.build_sensitivity_report(schema.read_table(EVENTS), models).encode("utf-8")


RESCHEDULE_COLUMNS = ("event_id", "model_id", "event_type", "platform", "source",
                      "source_url", "first_party", "from_date", "to_date",
                      "days_moved", "observed_on")


def build_reschedule_rows(events: list, claims: list) -> list:
    """One row per time a source moved its date for an event: each
    superseded claim paired with the next statement from the same source
    (the next superseded one by observation date, else the live one).
    `days_moved` is signed: positive means the date slipped later."""
    by_event = {e["event_id"]: e for e in events}
    by_source: dict = {}
    for c in claims:
        by_source.setdefault((c["event_id"], urlparse(c["source_url"]).netloc), []).append(c)
    rows = []
    for (event_id, _), group in by_source.items():
        history = sorted((c for c in group if c["superseded_on"]),
                         key=lambda c: (c["superseded_on"], c["date"]))
        if not history:
            continue
        # A source with several live claims (rare) is read as assess reads
        # it: by its earliest statement.
        live = min((c for c in group if not c["superseded_on"]), key=lambda c: c["date"])
        e = by_event[event_id]
        for old, new in zip(history, history[1:] + [live]):
            moved = (date.fromisoformat(new["date"]) - date.fromisoformat(old["date"])).days
            rows.append({
                "event_id": event_id, "model_id": e["model_id"],
                "event_type": e["event_type"], "platform": e["platform"],
                "source": old["label"].split(" (")[0], "source_url": old["source_url"],
                "first_party": old["first_party"], "from_date": old["date"],
                "to_date": new["date"], "days_moved": str(moved),
                "observed_on": old["superseded_on"],
            })
    return sorted(rows, key=lambda r: (r["event_id"], r["source_url"], r["observed_on"], r["from_date"]))


def build_reschedules_bytes() -> bytes:
    rows = build_reschedule_rows(schema.read_table(EVENTS), schema.read_table(schema.CLAIMS))
    return _csv_bytes(list(RESCHEDULE_COLUMNS), rows)


# Every generated artifact, with the function that rebuilds it from the
# core tables. `main` writes them; validate.py rule 9 byte-compares them.
GENERATED_ARTIFACTS = (
    ("llm_ledger_wide.csv", build_wide_bytes),
    ("llm_ledger_enriched.csv", build_enriched_bytes),
    ("models_latest.csv", build_latest_bytes),
    ("coverage_report.md", build_coverage_bytes),
    ("sensitivity_report.md", build_sensitivity_bytes),
    ("reschedules.csv", build_reschedules_bytes),
)


def main() -> int:
    models = compute_derived(schema.read_table(MODELS), schema.read_table(EVENTS))
    schema.write_table(MODELS, models)
    print("build: derived fields recomputed on data/core/models.csv")

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    for filename, regenerate in GENERATED_ARTIFACTS:
        try:
            payload = regenerate()
        except FileNotFoundError as exc:
            # Only the Epoch join needs a raw snapshot; nothing is invented.
            print(f"build: SKIPPED {filename} ({exc})")
            continue
        (GENERATED_DIR / filename).write_bytes(payload)
        print(f"build: wrote data/generated/{filename}")
    (schema.REPO_ROOT / "README.md").write_bytes(build_readme_bytes())
    print("build: refreshed the README stats block")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
