"""Pull Hugging Face Hub repo metadata for the census.

Sweeps the curated lab namespaces (Chinese labs enumerated per the coverage
priorities, plus Western open-weight publishers) and the global
`text-generation` top downloads. Stores a normalized CSV snapshot under
data/raw/hf/{date}/; loading into core tables is done by hf_census.py.

The repo `createdAt` timestamp is the primary machine source for
`weights_released` events - except the 2022-03-02 backfill artifact, which
is flagged, never used.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from huggingface_hub import HfApi

sys.path.insert(0, str(Path(__file__).resolve().parent))

import schema

# HF namespace -> ledger org_id. Chinese labs from the coverage priority
# list first, then Western open-weight publishers.
NAMESPACE_TO_ORG = {
    "Qwen": "alibaba",
    "deepseek-ai": "deepseek",
    "moonshotai": "moonshot",
    "zai-org": "zhipu", "THUDM": "zhipu",
    "baidu": "baidu",
    "tencent": "tencent",
    "MiniMaxAI": "minimax",
    "ByteDance-Seed": "bytedance", "ByteDance": "bytedance",
    "meituan-longcat": "meituan",
    "XiaomiMiMo": "xiaomi",
    "01-ai": "01ai",
    "baichuan-inc": "baichuan",
    "iflytek": "iflytek",
    "stepfun-ai": "stepfun",
    "internlm": "shanghai-ai-lab",
    "openbmb": "openbmb",
    "IEITYuan": "ieit",
    "Skywork": "skywork",
    "RWKV": "rwkv", "BlinkDL": "rwkv",
    "inclusionAI": "ant-group",
    "openai": "openai",
    "meta-llama": "meta",
    "mistralai": "mistral",
    "google": "google",
    "CohereLabs": "cohere", "CohereForAI": "cohere",
    "xai-org": "xai",
    "microsoft": "microsoft",
    "nvidia": "nvidia",
    "ibm-granite": "ibm",
    "allenai": "allenai",
    "tiiuae": "tii",
    "LiquidAI": "liquid-ai",
    "HuggingFaceTB": "huggingface",
    "NousResearch": "nous-research",
    "Snowflake": "snowflake",
    "databricks": "databricks",
    "ai21labs": "ai21",
    "EleutherAI": "eleutherai",
    "stabilityai": "stability",
}

IN_SCOPE_PIPELINES = {"text-generation", "image-text-to-text"}
PER_NAMESPACE_LIMIT = 60
GLOBAL_TOP_LIMIT = 300

COLUMNS = ["repo_id", "namespace", "org_id", "created_at", "downloads",
           "pipeline_tag", "license", "tags"]


def _rows_from(models, org_id: str = "") -> list:
    rows = []
    for m in models:
        namespace = m.id.split("/")[0] if "/" in m.id else ""
        created = ""
        if getattr(m, "created_at", None):
            created = m.created_at.date().isoformat()
        license_tag = next(
            (t.split(":", 1)[1] for t in (m.tags or []) if t.startswith("license:")), "")
        rows.append({
            "repo_id": m.id,
            "namespace": namespace,
            "org_id": org_id or NAMESPACE_TO_ORG.get(namespace, ""),
            "created_at": created,
            "downloads": getattr(m, "downloads", "") or 0,
            "pipeline_tag": getattr(m, "pipeline_tag", "") or "",
            "license": license_tag,
            "tags": "|".join(m.tags or []),
        })
    return rows


def main() -> int:
    api = HfApi()
    expand = ["createdAt", "downloads", "tags", "pipeline_tag"]
    all_rows: dict = {}

    for namespace, org_id in NAMESPACE_TO_ORG.items():
        try:
            models = api.list_models(
                author=namespace, expand=expand, limit=PER_NAMESPACE_LIMIT,
                sort="downloads",
            )
            rows = _rows_from(models, org_id)
        except Exception as exc:  # network/HTTP failure for one org: report, continue
            print(f"pull_hf: WARN namespace {namespace} failed: {exc}")
            continue
        for row in rows:
            all_rows[row["repo_id"]] = row
        print(f"pull_hf: {namespace}: {len(rows)} repos")

    try:
        top = api.list_models(
            pipeline_tag="text-generation", expand=expand,
            limit=GLOBAL_TOP_LIMIT, sort="downloads",
        )
        top_rows = _rows_from(top)
        for row in top_rows:
            all_rows.setdefault(row["repo_id"], row)
        print(f"pull_hf: global text-generation top: {len(top_rows)} repos")
    except Exception as exc:
        print(f"pull_hf: WARN global sweep failed: {exc}")

    # Repos already in the ledger stay tracked even after they fall out of
    # the download-ranked sweep; otherwise their weights date would vanish.
    tracked = [r["identifier"] for r in schema.read_table(schema.CROSSWALK)
               if r["namespace"] == "huggingface" and r["identifier"] not in all_rows]
    fetched = 0
    for repo_id in tracked:
        try:
            info = api.model_info(repo_id, expand=expand)
        except Exception as exc:  # deleted/gated repo: report, keep going
            print(f"pull_hf: WARN tracked repo {repo_id} failed: {exc}")
            continue
        all_rows[repo_id] = _rows_from([info])[0]
        fetched += 1
    print(f"pull_hf: tracked repos outside the sweep: {len(tracked)}, refetched {fetched}")

    if not all_rows:
        raise RuntimeError("pull_hf produced zero rows; Hub unreachable or API changed")

    out = schema.snapshot_dir("hf") / "normalized.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for repo_id in sorted(all_rows):
            writer.writerow(all_rows[repo_id])

    manifest = schema.snapshot_dir("hf") / "manifest.json"
    if not manifest.exists():
        import json
        manifest.write_text(json.dumps({
            "normalized.csv": {
                "url": "https://huggingface.co/api/models (org sweep + top downloads)",
                "rows": len(all_rows),
            }}, indent=2) + "\n", encoding="utf-8")
    print(f"pull_hf: {len(all_rows)} repos -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
