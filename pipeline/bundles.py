"""Export the four dataset bundles (Markets, Science, Lineage, Governance)
as zip files under dist/bundles/.

Each bundle is a set of CSVs taken from the core, observation and
generated tables, plus its methods page (docs/bundles/<name>.md) and the
data license. A file is a whole table or the rows of `events.csv` of the
bundle's event types, with the `claims.csv` rows behind them; nothing is
recomputed or stored, so `model_id` and `org_id` mean the same thing in
every bundle. Every bundle carries `models.csv` and `organizations.csv`.

Usage:
    python pipeline/bundles.py
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import schema

OUT_DIR = schema.REPO_ROOT / "dist" / "bundles"
DOCS_DIR = schema.REPO_ROOT / "docs" / "bundles"
CORE, OBS, GEN = "data/core", "data/observations", "data/generated"
IDENTITY = (f"{CORE}/models.csv", f"{CORE}/organizations.csv")

# name -> (whole tables, event types exported as events.csv + claims.csv)
BUNDLES = {
    "markets": (
        (f"{CORE}/attributes.csv", f"{OBS}/availability_observations.csv",
         f"{OBS}/price_observations.csv", f"{OBS}/capability_observations.csv",
         f"{OBS}/download_observations.csv", f"{OBS}/usage_observations.csv",
         f"{GEN}/market_on_date.csv", f"{GEN}/price_changes.csv", f"{GEN}/obsolescence.csv"),
        {"api_preview", "api_ga", "free_tier", "consumer_rollout", "platform_availability",
         "price_changed", "retired"},
    ),
    "science": (
        (f"{OBS}/research_mentions.csv", f"{OBS}/citation_observations.csv",
         f"{GEN}/research_mentions_monthly.csv",
         f"{GEN}/research_first_mentions.csv", f"{OBS}/model_versions.csv",
         f"{GEN}/llm_ledger_capability.csv", f"{GEN}/llm_ledger_benchmarks.csv",
         f"{GEN}/llm_ledger_arena.csv"),
        {"paper_published", "weights_released", "version_observed"},
    ),
    "lineage": (
        (f"{CORE}/crosswalk.csv", f"{GEN}/hub_descendants.csv"),
        {"announced", "weights_released", "license_changed", "renamed", "alias_repointed"},
    ),
    "governance": (
        (f"{GEN}/reschedules.csv",),
        {"license_changed", "deprecation_announced", "retired", "system_card", "paper_published"},
    ),
}


def _csv(rows: list, columns: tuple) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def bundle_files(name: str) -> dict:
    """{archive path: bytes} for one bundle."""
    tables, event_types = BUNDLES[name]
    files = {path.rsplit("/", 1)[-1]: (schema.REPO_ROOT / path).read_bytes()
             for path in IDENTITY + tables}
    events = [e for e in schema.read_table(schema.EVENTS) if e["event_type"] in event_types]
    ids = {e["event_id"] for e in events}
    files["events.csv"] = _csv(events, schema.EVENTS.columns)
    files["claims.csv"] = _csv([c for c in schema.read_table(schema.CLAIMS) if c["event_id"] in ids],
                               schema.CLAIMS.columns)
    files["METHODS.md"] = (DOCS_DIR / f"{name}.md").read_bytes()
    files["LICENSE"] = (schema.REPO_ROOT / "LICENSE").read_bytes()
    return files


def write_bundle(name: str, out_dir: Path = OUT_DIR) -> Path:
    """Write dist/bundles/llm-ledger-<name>.zip; entries carry a fixed
    timestamp so the same inputs give the same bytes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"llm-ledger-{name}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, payload in sorted(bundle_files(name).items()):
            zf.writestr(zipfile.ZipInfo(f"llm-ledger-{name}/{arcname}", (1980, 1, 1, 0, 0, 0)),
                        payload, zipfile.ZIP_DEFLATED)
    return path


def main() -> int:
    for name in BUNDLES:
        path = write_bundle(name)
        print(f"bundles: {name} -> {path.relative_to(schema.REPO_ROOT)} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
