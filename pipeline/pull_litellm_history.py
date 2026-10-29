"""Backfill LiteLLM's price table, one copy per day, from its git history.

For every calendar day from the file's first commit to `--until`, the copy
is the file as it stood on LiteLLM's `main` at the end of that day (UTC):
the last first-parent commit dated on or before the day. Each day becomes
data/raw/litellm_git/YYYY-MM-DD/ holding a manifest (the raw URL pinned to
that commit, the file's sha256) and a link to the gzipped copy under
data/raw/litellm_git/blobs/, so observe.py folds the days into price and
limit runs under the source `litellm_git`.

A commit date is when LiteLLM recorded a price, not when the provider
changed it; it bounds the provider's change from above. A copy that does
not parse as JSON gets a manifest with the error and no payload: that day
is a gap and ends every run.

Usage:
    python pipeline/pull_litellm_history.py
    python pipeline/pull_litellm_history.py --repo ~/.cache/llm-ledger/litellm --until 2026-10-02

`--until` defaults to the day before the first daily `litellm` price
observation, so the two sources meet without overlapping.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import schema

SOURCE = "litellm_git"
REPO_URL = "https://github.com/BerriAI/litellm.git"
FILE = "model_prices_and_context_window.json"
RAW_URL = "https://raw.githubusercontent.com/BerriAI/litellm/{commit}/" + FILE
DEFAULT_REPO = Path.home() / ".cache" / "llm-ledger" / "litellm"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout


def sync_repo(repo: Path) -> None:
    """A blobless clone of LiteLLM's main: history without file contents;
    each needed copy is fetched on first read."""
    if repo.exists():
        _git(repo, "fetch", "--quiet", "origin", "main")
        return
    repo.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", "--no-checkout",
                    "--single-branch", "--branch", "main", REPO_URL, str(repo)], check=True)


def commits_by_day(log: str) -> dict:
    """UTC day -> the last first-parent commit that day, from `git log
    --first-parent --reverse --format='%H %cI'` output. Commits must come
    in date order; out-of-order dates would make 'the file at the end of the
    day' ambiguous, so they fail."""
    by_day: dict = {}
    previous = None
    for line in log.splitlines():
        sha, stamp = line.split()
        when = datetime.fromisoformat(stamp).astimezone(timezone.utc)
        if previous is not None and when < previous:
            raise ValueError(f"litellm_git: commit {sha} ({when}) is dated before its "
                             f"first parent ({previous})")
        previous = when
        by_day[when.date()] = (sha, when.isoformat(timespec="seconds"))
    return by_day


def day_commits(by_day: dict, until: date) -> list:
    """(day, commit, committed_at) for every day from the first commit to
    `until`: the newest commit on or before each day."""
    days = sorted(by_day)
    if not days or days[0] > until:
        raise ValueError(f"litellm_git: no commit of {FILE} on or before {until}")
    out, current, day = [], None, days[0]
    while day <= until:
        current = by_day.get(day, current)
        out.append((day, *current))
        day += timedelta(days=1)
    return out


def default_until() -> date:
    """The day before the first daily `litellm` price observation."""
    path = schema.OBSERVATIONS_DIR / schema.PRICE_OBSERVATIONS.filename
    firsts = [r["first_observed"] for r in schema.read_table(schema.PRICE_OBSERVATIONS,
                                                             schema.OBSERVATIONS_DIR)
              if r["source"] == "litellm"]
    if not firsts:
        raise SystemExit(f"litellm_git: {path} holds no litellm runs; pass --until")
    return date.fromisoformat(min(firsts)) - timedelta(days=1)


def read_blob(repo: Path, blob: str, attempts: int = 3) -> bytes:
    """One copy's bytes; the blobless clone fetches it from GitHub on first
    read, which can fail transiently, so it is retried."""
    for attempt in range(attempts):
        if attempt:
            time.sleep(5 * attempt)
        result = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", blob],
                                capture_output=True)
        if result.returncode == 0:
            return result.stdout
    raise RuntimeError(f"litellm_git: cannot read blob {blob}: "
                       f"{result.stderr.decode(errors='replace').strip()}")


def store_blob(repo: Path, blob: str, blobs_dir: Path) -> tuple:
    """Write one copy gzipped (fixed mtime, so reruns are byte-identical)
    and return (sha256, bytes, parse error or "")."""
    path = blobs_dir / f"{blob}.json.gz"
    content = gzip.decompress(path.read_bytes()) if path.exists() else read_blob(repo, blob)
    try:
        json.loads(content)
        error = ""
    except json.JSONDecodeError as exc:
        error = f"not valid JSON: {exc}"
    if not path.exists():
        path.write_bytes(gzip.compress(content, mtime=0))
    return hashlib.sha256(content).hexdigest(), len(content), error


def write_day(day_dir: Path, blob_path: Path, entry: dict) -> None:
    day_dir.mkdir(parents=True, exist_ok=True)
    link = day_dir / f"{FILE}.gz"
    if link.is_symlink() or link.exists():
        link.unlink()
    if "sha256" in entry:
        link.symlink_to(Path("..") / "blobs" / blob_path.name)
    (day_dir / "manifest.json").write_text(
        json.dumps({FILE: entry}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO,
                        help="blobless clone of BerriAI/litellm (made if missing)")
    parser.add_argument("--until", type=date.fromisoformat, help="last day to write")
    args = parser.parse_args()
    until = args.until or default_until()
    sync_repo(args.repo)
    log = _git(args.repo, "log", "--first-parent", "--reverse", "--format=%H %cI",
               "origin/main", "--", FILE)
    days = day_commits(commits_by_day(log), until)
    commits = sorted({c for _, c, _ in days})
    blob_of = dict(zip(commits, _git(args.repo, "rev-parse",
                                     *(f"{c}:{FILE}" for c in commits)).split()))
    root = schema.RAW_DIR / SOURCE
    blobs_dir = root / "blobs"
    blobs_dir.mkdir(parents=True, exist_ok=True)
    stored: dict = {}
    for i, commit in enumerate(commits, 1):
        stored[commit] = store_blob(args.repo, blob_of[commit], blobs_dir)
        if i % 100 == 0:
            print(f"litellm_git: read {i}/{len(commits)} copies")
    gaps = 0
    for day, commit, committed_at in days:
        sha256, size, error = stored[commit]
        entry = {"url": RAW_URL.format(commit=commit), "commit": commit,
                 "committed_at": committed_at, "bytes": size}
        if error:
            entry["error"] = error
            gaps += 1
        else:
            entry["sha256"] = sha256
        write_day(root / day.isoformat(), blobs_dir / f"{blob_of[commit]}.json.gz", entry)
    print(f"litellm_git: {len(days)} days {days[0][0]}..{days[-1][0]} from {len(commits)} "
          f"commits; {gaps} days without a parseable copy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
