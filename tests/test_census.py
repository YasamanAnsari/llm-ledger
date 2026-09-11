"""hf_census.census over in-memory tables: identity, attribution, scope."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import schema
from hf_census import census, unmapped_namespace_leads

TODAY, NOW = date(2026, 10, 1), "2026-10-01T00:00:00+00:00"


def _repo(repo_id, org_id, created, tag="text-generation", downloads=100,
          license="apache-2.0", tags=""):
    return {"repo_id": repo_id, "namespace": repo_id.split("/")[0], "org_id": org_id,
            "created_at": created, "downloads": downloads, "pipeline_tag": tag,
            "license": license, "tags": tags}


def _tables():
    orgs = [{c: "" for c in schema.ORGANIZATIONS.columns}
            | {"org_id": o, "canonical_name": o, "short_name": o, "country": "US",
               "org_type": "ai_lab", "is_active": "true"}
            for o in ("meta", "nous-research", "alibaba")]
    return {"organizations": orgs, "models": [], "events": [], "claims": [],
            "crosswalk": [], "attributes": []}


def test_mirror_never_drafts_and_official_repo_owns_the_model():
    t = _tables()
    repos = [_repo("NousResearch/Meta-Llama-3.1-70B", "nous-research", "2024-07-14"),
             _repo("meta-llama/Llama-3.1-70B", "meta", "2024-07-16")]
    outcomes, review = census(repos, t, {}, TODAY, NOW)
    (m,) = t["models"]
    assert (m["model_id"], m["developer_org_id"]) == ("llama-3-1-70b", "meta")
    assert [r["identifier"] for r in t["crosswalk"]] == ["meta-llama/Llama-3.1-70B"]
    assert t["events"][0]["date"] == "2024-07-16"
    assert [r["kind"] for r in review] == ["hf_mirror_repo"]
    assert outcomes["models"] == 1 and outcomes["added"] == 1


def test_format_variants_and_roles():
    t = _tables()
    repos = [_repo("Qwen/Qwen2.5-72B", "alibaba", "2024-09-16"),
             _repo("Qwen/Qwen2.5-72B-Instruct", "alibaba", "2024-09-16"),
             _repo("Qwen/Qwen2.5-72B-Instruct-FP8", "alibaba", "2024-09-17")]
    census(repos, t, {}, TODAY, NOW)
    ids = sorted(m["model_id"] for m in t["models"])
    assert ids == ["qwen2-5-72b", "qwen2-5-72b-instruct"]  # base and instruct distinct
    xw = {r["identifier"] for r in t["crosswalk"] if r["model_id"] == "qwen2-5-72b-instruct"}
    assert xw == {"Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-72B-Instruct-FP8"}  # FP8 is packaging


def test_derivative_under_publisher_and_recreated_repo_guard():
    t = _tables()
    repos = [_repo("NousResearch/Hermes-3-Llama-3.1-8B", "nous-research", "2024-08-15")]
    _, review = census(repos, t, {"NousResearch/Hermes-3-Llama-3.1-8B": "2024-01-01"}, TODAY, NOW)
    (m,) = t["models"]
    assert (m["developer_org_id"], m["is_derivative"], m["derivative_type"]) == \
        ("nous-research", "true", "finetune")
    assert t["events"][0]["confidence"] == "inferred" and len(t["claims"]) == 1
    assert [r["kind"] for r in review] == ["hf_recreated_repo"]


def test_unmapped_namespaces_become_one_lead_each():
    repos = [_repo("newlab/NewLab-7B", "", "2026-01-01"),
             _repo("newlab/NewLab-70B", "", "2026-01-02"),
             _repo("quantizer/NewLab-7B-GGUF", "", "2026-01-03"),   # excluded by name
             _repo("meta-llama/Llama-3.1-70B", "meta", "2024-07-16")]
    (lead,) = unmapped_namespace_leads(repos)
    assert (lead["kind"], lead["left_key"]) == ("hf_unmapped_namespace", "newlab")
    assert lead["note"].startswith("2 in-scope repos")
