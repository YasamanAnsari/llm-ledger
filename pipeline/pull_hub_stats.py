"""Weekly Hugging Face download counts for the ledger's Hub repos, from
the history of the `cfahlgren1/hub-stats` dataset (Apache-2.0).

The dataset's maintainer uploads a fresh `models.parquet` (every public
Hub model with its `downloads`, the Hub's rolling 30-day count, and since
2025 `downloadsAllTime`) most days since 2024-07-29. For each ISO week the
first upload is read at its pinned revision, only the `id` and download
columns, and only repos the crosswalk maps to a ledger model are kept:
data/raw/hub_stats/YYYY-MM-DD/normalized.csv (the upload's UTC day) plus a
manifest naming the revision and the file's sha256. observe.py folds the
days into download_observations under the source `hub_stats`.

A week with no upload has no row. Values are copied as stated; a column
the revision does not carry stays blank. Repos added to the crosswalk
later are not in weeks already pulled: delete those day directories and
re-run to add them.

The newest week also gets descendants.csv: for each ledger repo, how many
Hub repos name it as a direct base model, by the Hub's stated relation
(`finetune`, `quantized`, `merge`, `adapter`), from the same revision's
`baseModels` column. Derivatives of derivatives count only toward their
own base.

Usage:
    python pipeline/pull_hub_stats.py              # every week not yet pulled
    python pipeline/pull_hub_stats.py --limit 5    # at most 5 weeks this run
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import HfApi, HfFileSystem

sys.path.insert(0, str(Path(__file__).resolve().parent))

import schema

SOURCE = "hub_stats"
DATASET = "cfahlgren1/hub-stats"
FILE = "models.parquet"
URL = f"https://huggingface.co/datasets/{DATASET}/blob/{{revision}}/{FILE}"
COLUMNS = ("repo_id", "downloads", "downloads_all_time")
DESCENDANT_COLUMNS = ("repo_id", "relation", "descendants")
# ponytail: one snapshot a week (Paper 5's cadence); a read costs ~50 s and
# ~80 MB because the id column cannot be skipped. Daily would be ~7x that.


def weekly_uploads(commits: list) -> list:
    """(day, revision, committed_at) of the first `models.parquet` upload in
    each ISO week, oldest first. `commits` are (revision, UTC datetime,
    title) from the dataset's history; an upload's title names the file."""
    first: dict = {}
    for revision, when, title in sorted(commits, key=lambda c: c[1]):
        if FILE in title:
            first.setdefault(when.isocalendar()[:2], (when.date(), revision,
                                                      when.isoformat(timespec="seconds")))
    return sorted(first.values())


def ledger_repos() -> set:
    return {r["identifier"] for r in schema.read_table(schema.CROSSWALK)
            if r["namespace"] == "huggingface"}


def read_downloads(fs: HfFileSystem, revision: str, repos: set) -> list:
    """Download counts of `repos` in one revision of models.parquet."""
    path = f"datasets/{DATASET}@{revision}/{FILE}"
    with fs.open(path, "rb") as fh:
        names = set(pq.ParquetFile(fh).schema_arrow.names)
    if not {"id", "downloads"} <= names:
        raise ValueError(f"hub_stats: {revision} lacks id or downloads; columns are {sorted(names)}")
    columns = ["id", "downloads"] + (["downloadsAllTime"] if "downloadsAllTime" in names else [])
    table = pq.read_table(path, columns=columns, filesystem=fs).to_pylist()
    return sorted(({"repo_id": r["id"], "downloads": _text(r["downloads"]),
                    "downloads_all_time": _text(r.get("downloadsAllTime"))}
                   for r in table if r["id"] in repos), key=lambda r: r["repo_id"])


def _text(value) -> str:
    return "" if value is None else str(value)


def descendant_counts(base_models: list, repos: set) -> list:
    """{repo_id, relation, descendants} for each of `repos` some Hub repo
    names as a base. `base_models` are models.parquet `baseModels` values:
    {relation, models: [{id}]}, or None for a repo naming no base."""
    counts: Counter = Counter()
    for entry in base_models:
        if entry:
            for base in {m["id"] for m in entry["models"] or ()} & repos:
                counts[(base, entry["relation"])] += 1
    return [{"repo_id": repo, "relation": relation, "descendants": str(n)}
            for (repo, relation), n in sorted(counts.items())]


def read_descendants(fs: HfFileSystem, revision: str, repos: set) -> list:
    path = f"datasets/{DATASET}@{revision}/{FILE}"
    with fs.open(path, "rb") as fh:
        if "baseModels" not in pq.ParquetFile(fh).schema_arrow.names:
            raise ValueError(f"hub_stats: {revision} has no baseModels column")
    column = pq.read_table(path, columns=["baseModels"], filesystem=fs).column("baseModels")
    return descendant_counts(column.to_pylist(), repos)


def _write_csv(path: Path, columns: tuple, rows: list) -> None:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8")


def write_day(day_dir: Path, rows: list, entry: dict) -> None:
    day_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(day_dir / "normalized.csv", COLUMNS, rows)
    (day_dir / "manifest.json").write_text(
        json.dumps({FILE: entry}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="pull at most this many weeks")
    args = parser.parse_args()
    api, fs = HfApi(), HfFileSystem()
    commits = [(c.commit_id, c.created_at.astimezone(timezone.utc), c.title)
               for c in api.list_repo_commits(DATASET, repo_type="dataset")]
    root = schema.RAW_DIR / SOURCE
    todo = [w for w in weekly_uploads(commits)
            if not (root / w[0].isoformat() / "normalized.csv").exists()]
    repos = ledger_repos()
    for day, revision, committed_at in todo[:args.limit]:
        info = api.get_paths_info(DATASET, [FILE], repo_type="dataset", revision=revision)[0]
        rows = read_downloads(fs, revision, repos)
        if not rows:
            raise ValueError(f"hub_stats: {revision} holds none of the {len(repos)} ledger repos")
        write_day(root / day.isoformat(), rows, {
            "url": URL.format(revision=revision), "revision": revision,
            "committed_at": committed_at, "sha256": info.lfs.sha256, "bytes": info.size,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        print(f"hub_stats: {day} ({revision[:10]}): {len(rows)} of {len(repos)} ledger repos")
    day, revision, _ = weekly_uploads(commits)[-1]
    newest = root / day.isoformat()
    if (newest / "normalized.csv").exists() and not (newest / "descendants.csv").exists():
        rows = read_descendants(fs, revision, repos)
        _write_csv(newest / "descendants.csv", DESCENDANT_COLUMNS, rows)
        print(f"hub_stats: {day}: descendants of {len({r['repo_id'] for r in rows})} ledger repos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
