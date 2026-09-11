"""repair.py: table surgery that keeps every FK and claim consistent."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import repair
import schema


def _tables():
    def m(mid, **o):
        return {c: "" for c in schema.MODELS.columns} | {
            "model_id": mid, "developer_org_id": "acme", "model_type": "llm",
            "access_type": "open_weights", "is_derivative": "false", "review_status": "unreviewed"} | o

    def e(eid, mid, et, d, st="hf_hub", **o):
        return {c: "" for c in schema.EVENTS.columns} | {
            "event_id": eid, "model_id": mid, "event_type": et, "date": d, "precision": "day",
            "region": "global", "source_url": "https://huggingface.co/acme/x", "source_type": st,
            "confidence": "inferred"} | o

    def c(eid, url, d, label="hub repo created", st="hf_hub"):
        return {"event_id": eid, "source_url": url, "source_type": st, "date": d, "precision": "day",
                "label": label, "bound": "true", "first_party": "false"}

    return {
        "organizations": [], "attributes": [{"model_id": "x-fp8", "context_length": "1"}],
        "models": [m("x"), m("x-fp8"), m("y", base_model_id="x-fp8")],
        "events": [e("x-weights_released-1", "x", "weights_released", "2025-01-02"),
                   e("x-fp8-weights_released-1", "x-fp8", "weights_released", "2025-01-01"),
                   e("x-fp8-retired-1", "x-fp8", "retired", "2026-01-01", platform="aws_bedrock",
                     st="lifecycle_table")],
        "claims": [c("x-weights_released-1", "https://huggingface.co/acme/x", "2025-01-02"),
                   c("x-fp8-weights_released-1", "https://huggingface.co/acme/x-fp8", "2025-01-01"),
                   c("x-fp8-retired-1", "https://aws/lifecycle", "2026-01-01", "bedrock_lifecycle",
                     "lifecycle_table")],
        "crosswalk": [{"model_id": "x", "namespace": "huggingface", "identifier": "acme/x"},
                      {"model_id": "x-fp8", "namespace": "huggingface", "identifier": "acme/x-fp8"}],
    }


def test_merge_moves_crosswalk_claims_and_missing_events_then_deletes():
    t = _tables()
    repair.merge_models(t, keep="x", drop="x-fp8")
    assert {m["model_id"] for m in t["models"]} == {"x", "y"}
    assert t["models"][-1]["base_model_id"] == "x"                       # FK re-pointed
    assert {r["identifier"] for r in t["crosswalk"] if r["model_id"] == "x"} == {"acme/x", "acme/x-fp8"}
    ids = {e["event_id"] for e in t["events"]}
    assert ids == {"x-weights_released-1", "x-retired-1"}                 # duplicate type dropped, new type moved
    assert {c["event_id"] for c in t["claims"]} == ids
    assert t["attributes"][0]["model_id"] == "x"


def test_rename_reids_events_and_claims():
    t = _tables()
    repair.rename_model(t, "x-fp8", "z")
    assert {e["event_id"] for e in t["events"] if e["model_id"] == "z"} == {"z-weights_released-1", "z-retired-1"}
    assert all(c["event_id"].startswith("z-") for c in t["claims"]
               if "fp8" in c["source_url"] or "aws" in c["source_url"])
    assert t["models"][2]["base_model_id"] == "z"


def test_delete_retag_detach_and_claim_resets():
    t = _tables()
    assert repair.retag_platform(t, "aws_bedrock", "bedrock") == 1
    assert repair.detach_crosswalk(t, "x", "huggingface", "acme/x")
    assert repair.delete_models(t, {"x-fp8"}) == 1
    assert not any(c["event_id"].startswith("x-fp8") for c in t["claims"])
    assert t["models"][-1]["base_model_id"] == ""                        # dangling FK blanked
    t = _tables()
    t["claims"].append({"event_id": "x-weights_released-1", "source_url": "https://web.archive.org/x",
                        "source_type": "wayback", "date": "2024-12-01", "precision": "day",
                        "label": "first public capture", "bound": "true", "first_party": "false"})
    t["events"][0].update({"source_type": "wayback", "date": "2024-12-01"})
    repair.reset_to_hub_claim(t, "x-weights_released-1", date(2026, 10, 1))
    ev = t["events"][0]
    assert (ev["source_type"], ev["date"], ev["confidence"]) == ("hf_hub", "2025-01-02", "inferred")
    assert [c["label"] for c in t["claims"] if c["event_id"] == ev["event_id"]] == ["hub repo created"]
    t = _tables()
    t["claims"] = [c for c in t["claims"] if c["event_id"] != "x-weights_released-1"]
    t["events"][0].update({"source_type": "api_metadata",
                           "source_url": "https://epoch.ai/data/all_ai_models.csv", "notes": ""})
    repair.backfill_single_claim(t, "x-weights_released-1", "epoch.ai")
    (claim,) = [c for c in t["claims"] if c["event_id"] == "x-weights_released-1"]
    assert (claim["label"], claim["date"], claim["bound"]) == ("epoch.ai", "2025-01-02", "false")
    assert t["events"][0]["notes"] == "single source: epoch.ai 2025-01-02"


def test_reset_without_a_hub_claim_removes_the_event():
    t = _tables()
    t["claims"] = [{"event_id": "x-weights_released-1", "source_url": "https://web.archive.org/x",
                    "source_type": "wayback", "date": "2024-12-01", "precision": "day",
                    "label": "first public capture", "bound": "true", "first_party": "false"}]
    t["events"][0].update({"source_type": "wayback", "date": "2024-12-01"})
    assert repair.reset_to_hub_claim(t, "x-weights_released-1", date(2026, 10, 1)) is False
    assert not any(e["event_id"] == "x-weights_released-1" for e in t["events"])
    assert not any(c["event_id"] == "x-weights_released-1" for c in t["claims"])
