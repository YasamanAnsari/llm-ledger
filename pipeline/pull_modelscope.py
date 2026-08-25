"""Pull ModelScope model metadata (requires MODELSCOPE_TOKEN).

ModelScope's OpenAPI requires OAuth; when no token is present this puller
skips cleanly - Hugging Face covers most Chinese open-weight releases, so
ModelScope adds coverage rather than gating it. No data is fabricated when
the source is unavailable.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch
import schema

API = "https://modelscope.cn/api/v1/models"

ORG_NAMESPACES = (
    "Qwen", "deepseek-ai", "moonshotai", "ZhipuAI", "baidu", "Tencent-Hunyuan",
    "MiniMax", "ByteDance-Seed", "XiaomiMiMo", "01ai", "baichuan-inc",
    "iflytek", "stepfun-ai", "Shanghai_AI_Laboratory", "OpenBMB", "IEITYuan",
    "Skywork", "RWKV", "inclusionAI",
)

COLUMNS = ["repo_id", "namespace", "created_at", "license", "downloads"]


def main() -> int:
    token = os.environ.get("MODELSCOPE_TOKEN", "")
    if not token:
        print("pull_modelscope: SKIP (MODELSCOPE_TOKEN not set; "
              "Hugging Face is the designated fallback for Chinese open weights)")
        return 0

    headers = {"Authorization": f"Bearer {token}"}
    rows = []
    for namespace in ORG_NAMESPACES:
        url = f"{API}?Owner={namespace}&PageSize=100"
        payload = json.loads(fetch.get_bytes(url, headers=headers))
        for m in (payload.get("Data") or {}).get("Models", []) or []:
            rows.append({
                "repo_id": f"{namespace}/{m.get('Name', '')}",
                "namespace": namespace,
                "created_at": m.get("CreatedTime", ""),
                "license": m.get("License", ""),
                "downloads": m.get("Downloads", ""),
            })
        print(f"pull_modelscope: {namespace}: swept")

    out = schema.snapshot_dir("modelscope") / "normalized.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: r["repo_id"]))
    print(f"pull_modelscope: {len(rows)} repos -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
