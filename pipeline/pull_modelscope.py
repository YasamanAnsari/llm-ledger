"""Sweep ModelScope's public search for the Chinese labs' repositories.

No token is needed. `PUT /api/v1/dolphin/models` with an `organizations`
criterion returns pages of one owner's models with `CreatedTime` (unix),
`LastUpdatedTime`, `License`, `Tasks[].Name` and `Downloads`. Repo creation
behaves like the Hub's `createdAt`: a bound on the public release, not the
release itself (Qwen3-8B was created 2025-04-28, launched 2025-04-29).
hf_census.py uses a twin repo here to corroborate the Hub date.

Filters verified against the live API on 2026-09-11: `organizations
contains` selects the owner, `tasks contains` the pipeline tags; the
`owner` category the site once used is ignored by the server.
"""

from __future__ import annotations

import csv
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch
import schema

SEARCH = "https://modelscope.cn/api/v1/dolphin/models"
PAGE_SIZE = 100
IN_SCOPE_TASKS = ("text-generation", "image-text-to-text")

# ModelScope owner -> ledger org_id, the same ids pull_hf.NAMESPACE_TO_ORG uses.
OWNER_TO_ORG = {
    "Qwen": "alibaba", "deepseek-ai": "deepseek", "moonshotai": "moonshot",
    "ZhipuAI": "zhipu", "baidu": "baidu", "Tencent-Hunyuan": "tencent",
    "MiniMax": "minimax", "ByteDance-Seed": "bytedance", "XiaomiMiMo": "xiaomi",
    "01ai": "01ai", "baichuan-inc": "baichuan", "iflytek": "iflytek",
    "stepfun-ai": "stepfun", "Shanghai_AI_Laboratory": "shanghai-ai-lab",
    "OpenBMB": "openbmb", "IEITYuan": "ieit", "Skywork": "skywork", "RWKV": "rwkv",
    "inclusionAI": "ant-group",
}

COLUMNS = ["repo_id", "namespace", "org_id", "created_at", "last_updated", "downloads",
           "task", "license"]


def _unix_date(value) -> str:
    return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat() if value else ""


def _page(owner: str, page: int) -> list:
    body = {"PageSize": PAGE_SIZE, "PageNumber": page, "SortBy": "Default", "Target": "",
            "SingleCriterion": [],
            "Criterion": [{"category": "organizations", "predicate": "contains", "values": [owner]},
                          {"category": "tasks", "predicate": "contains", "values": list(IN_SCOPE_TASKS)}]}
    response = requests.put(SEARCH, json=body, headers={"User-Agent": fetch.USER_AGENT},
                            timeout=fetch.TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("Success"):
        raise ValueError(f"ModelScope search failed for {owner}: {payload.get('Message')}")
    return payload["Data"]["Model"]["Models"] or []


def sweep(owner: str, org_id: str) -> list:
    """Every in-scope repo of one owner, as normalized rows."""
    rows, page = [], 1
    while True:
        models = _page(owner, page)
        for m in models:
            if m.get("Path") != owner:
                continue  # the criterion is a substring match; keep the exact owner
            tasks = {t.get("Name") for t in (m.get("Tasks") or [])}
            rows.append({
                "repo_id": f"{owner}/{m['Name']}", "namespace": owner, "org_id": org_id,
                "created_at": _unix_date(m.get("CreatedTime")),
                "last_updated": _unix_date(m.get("LastUpdatedTime")),
                "downloads": m.get("Downloads", 0),
                "task": next((t for t in IN_SCOPE_TASKS if t in tasks), ""),
                "license": (m.get("License") or "").lower(),
            })
        if len(models) < PAGE_SIZE:
            return rows
        page += 1


def main() -> int:
    rows = []
    for owner, org_id in OWNER_TO_ORG.items():
        found = sweep(owner, org_id)
        rows.extend(found)
        print(f"pull_modelscope: {owner}: {len(found)} repos")
    if not rows:
        raise RuntimeError("pull_modelscope produced zero rows; API unreachable or shape changed")

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(sorted(rows, key=lambda r: r["repo_id"]))
    out = schema.write_snapshot("modelscope", "normalized.csv", buf.getvalue().encode("utf-8"),
                                f"{SEARCH} (organizations sweep)")
    print(f"pull_modelscope: {len(rows)} repos -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
