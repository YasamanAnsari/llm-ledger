"""Pull capability scores (all CC BY 4.0) for the generated capability joins.

- Epoch Capabilities Index scores -> llm_ledger_capability.csv
- Epoch benchmark hub (per-benchmark scores) -> llm_ledger_benchmarks.csv
- LMArena leaderboard history, overall category -> llm_ledger_arena.csv

No score is ever copied into core tables (validation rule 10); build.py
joins these snapshots through the crosswalk. Artificial Analysis is not
pulled: its Terms of Use allow personal, noncommercial use of the site
only, and its data terms forbid republishing raw data, so rows Epoch
sourced from it are dropped in build.py as well.
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch
import schema

ECI_URL = "https://epoch.ai/data/eci_scores.csv"
ECI_SOURCE, ECI_FILE = "epoch_eci", "eci_scores.csv"
ECI_COLUMNS = ("Model", "eci", "eci_ci_low", "eci_ci_high", "date", "Accessibility group")

BENCH_URL = "https://epoch.ai/data/benchmark_data.zip"
BENCH_SOURCE, BENCH_FILE = "epoch_benchmarks", "benchmark_data.zip"
BENCH_MEMBERS = ("benchmark_metadata.csv", "model_metadata.csv")

ARENA_REPO = "lmarena-ai/leaderboard-dataset"
ARENA_SOURCE, ARENA_FILE = "lmarena", "leaderboard_overall.csv"
ARENA_CONFIGS = ("text", "text_style_control", "webdev", "vision")
ARENA_COLUMNS = ("model_name", "organization", "license", "rating", "rating_lower",
                 "rating_upper", "variance", "vote_count", "rank", "category",
                 "leaderboard_publish_date")


def check_eci(payload: bytes) -> int:
    """Rows in the payload; raises when a column the join reads is gone."""
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8")))
    missing = [c for c in ECI_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"ECI CSV lacks {missing}; header is {reader.fieldnames}")
    return sum(1 for _ in reader)


def check_benchmarks(payload: bytes) -> int:
    """Benchmarks listed in the zip's metadata; raises when a member is gone."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        missing = [m for m in BENCH_MEMBERS if m not in names]
        if missing:
            raise ValueError(f"benchmark zip lacks {missing}")
        meta = list(csv.DictReader(io.StringIO(archive.read("benchmark_metadata.csv").decode("utf-8"))))
    absent = [m["source_file"] for m in meta if m["source_file"] and m["source_file"] not in names]
    if absent:
        raise ValueError(f"benchmark_metadata.csv names files the zip lacks: {absent}")
    return len(meta)


def arena_overall_csv() -> tuple[bytes, str]:
    """The overall-category rows of each arena's full history, as one CSV.

    Pinned to the dataset commit it was read at; raises unless the dataset
    card still says CC BY 4.0.
    """
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    from huggingface_hub import HfApi, hf_hub_download

    info = HfApi().dataset_info(ARENA_REPO)
    license_id = (info.card_data or {}).get("license")
    if license_id != "cc-by-4.0":
        raise ValueError(f"{ARENA_REPO} license is {license_id!r}, not cc-by-4.0; not pulling")
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(("arena",) + ARENA_COLUMNS)
    for config in ARENA_CONFIGS:
        path = hf_hub_download(ARENA_REPO, f"{config}/full-00000-of-00001.parquet",
                               repo_type="dataset", revision=info.sha)
        table = pq.read_table(path, columns=list(ARENA_COLUMNS))
        overall = table.filter(pc.equal(table["category"], "overall"))
        for row in overall.to_pylist():
            writer.writerow((config,) + tuple("" if row[c] is None else row[c] for c in ARENA_COLUMNS))
    return buf.getvalue().encode("utf-8"), f"https://huggingface.co/datasets/{ARENA_REPO}/tree/{info.sha}"


def pull_eci() -> str:
    payload = fetch.get_bytes(ECI_URL)
    rows = check_eci(payload)
    schema.write_snapshot(ECI_SOURCE, ECI_FILE, payload, ECI_URL)
    return f"{rows} ECI rows"


def pull_benchmarks() -> str:
    payload = fetch.get_bytes(BENCH_URL)
    benchmarks = check_benchmarks(payload)
    schema.write_snapshot(BENCH_SOURCE, BENCH_FILE, payload, BENCH_URL)
    return f"{benchmarks} Epoch benchmarks"


def pull_arena() -> str:
    payload, url = arena_overall_csv()
    schema.write_snapshot(ARENA_SOURCE, ARENA_FILE, payload, url)
    rows = payload.count(b"\n") - 1
    return f"{rows} LMArena overall rows"


def main() -> int:
    failed = []
    for pull in (pull_eci, pull_benchmarks, pull_arena):
        try:
            print(f"pull_capability: {pull()}")
        except Exception as exc:  # one source down must not block the others; reported below
            print(f"pull_capability: {pull.__name__} failed: {exc}", file=sys.stderr)
            failed.append(pull.__name__)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
