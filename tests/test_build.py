"""Derived-field logic tests."""

from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import bundles
import schema
from build import (CAPABILITY_COLUMNS, LATEST_COLUMNS, _agent_section, build_reschedule_rows,
                   capability_rows, compute_derived, first_mention_rows, latest_first,
                   latest_pull_date, predecessor_review_rows, research_monthly_rows)
from confidence import curated_model_ids
from schema import MODELS, family_and_role


def _model(model_id="m1"):
    return {"model_id": model_id}


def _event(model_id, event_type, date, precision="day", region="global", confidence="inferred"):
    return {
        "model_id": model_id, "event_type": event_type, "date": date,
        "precision": precision, "region": region, "confidence": confidence,
    }


def test_min_availability_wins():
    events = [
        _event("m1", "api_ga", "2025-03-01"),
        _event("m1", "weights_released", "2025-04-01"),
    ]
    (row,) = compute_derived([_model()], events)
    assert row["first_public_availability_date"] == "2025-03-01"
    assert row["first_availability_via"] == "api_ga"


def test_weights_on_a_drafted_api_row_clear_the_proprietary_default():
    model = _model() | {"access_type": "api_only", "license": "proprietary",
                        "license_family": "proprietary"}
    (row,) = compute_derived([model], [_event("m1", "weights_released", "2025-03-01")])
    assert (row["access_type"], row["license"], row["license_family"]) == ("open_weights", "", "")


def test_tie_priority_weights_over_api():
    events = [
        _event("m1", "api_ga", "2025-03-01"),
        _event("m1", "weights_released", "2025-03-01"),
        _event("m1", "consumer_rollout", "2025-03-01"),
    ]
    (row,) = compute_derived([_model()], events)
    assert row["first_availability_via"] == "weights_released"


def test_person_read_launch_beats_a_late_unverified_listing():
    # Llama 3.1 405B Instruct: launched on Bedrock on 2024-07-23, then one
    # reseller listed it on 2026-09-10 and models.dev called that a release.
    launch = [_event("m1", "announced", "2024-07-23", confidence="verified"),
              {**_event("m1", "platform_availability", "2024-07-23", confidence="verified"),
               "source_type": "vendor_blog", "verified_by": "llm-ledger"}]
    (row,) = compute_derived([_model()], launch + [_event("m1", "weights_released", "2026-09-10")])
    assert row["first_public_availability_date"] == "2024-07-23"
    assert row["first_availability_via"] == "platform_availability_fallback"
    assert row["first_availability_confidence"] == "verified"
    # 155 days is GPT-4 Turbo's real preview-to-GA wait: a gap that short
    # keeps the GA date as the headline.
    (row,) = compute_derived([_model()], launch + [_event("m1", "api_ga", "2024-12-25")])
    assert row["first_public_availability_date"] == "2024-12-25"


def test_fallback_suffix():
    events = [_event("m1", "api_preview", "2025-02-01")]
    (row,) = compute_derived([_model()], events)
    assert row["first_public_availability_date"] == "2025-02-01"
    assert row["first_availability_via"] == "api_preview_fallback"


def test_non_global_region_ignored():
    events = [
        _event("m1", "api_ga", "2025-01-01", region="CN"),
        _event("m1", "api_ga", "2025-06-01"),
    ]
    (row,) = compute_derived([_model()], events)
    assert row["first_public_availability_date"] == "2025-06-01"


def test_anticipation_days():
    events = [
        _event("m1", "announced", "2025-01-10"),
        _event("m1", "api_ga", "2025-01-31"),
    ]
    (row,) = compute_derived([_model()], events)
    assert row["anticipation_days"] == "21"


def test_anticipation_null_when_precision_coarse():
    events = [
        _event("m1", "announced", "2025-01-01", precision="quarter"),
        _event("m1", "api_ga", "2025-01-31"),
    ]
    (row,) = compute_derived([_model()], events)
    assert row["anticipation_days"] == ""


def test_no_availability_leaves_fields_empty():
    events = [_event("m1", "announced", "2025-01-10")]
    (row,) = compute_derived([_model()], events)
    assert row["first_public_availability_date"] == ""
    assert row["first_availability_via"] == ""
    assert row["anticipation_days"] == ""


def test_latest_first_newest_top_undated_last_id_tiebreak():
    def row(model_id, date):
        return {"model_id": model_id, "first_public_availability_date": date}

    models = [row("b", "2025-03-01"), row("undated", ""), row("c", "2025-01-01"),
              row("a", "2025-03-01")]
    assert [r["model_id"] for r in latest_first(models)] == ["a", "b", "c", "undated"]
    assert LATEST_COLUMNS[0] == "first_public_availability_date"
    assert set(LATEST_COLUMNS) <= set(MODELS.columns) and len(set(LATEST_COLUMNS)) == len(LATEST_COLUMNS)


def test_family_and_role_from_name():
    cases = {
        "Qwen2.5-72B-Instruct": ("Qwen2.5", "instruct"),
        "Llama 3.1 405B Instruct": ("Llama 3.1", "instruct"),
        "o3-mini": ("o3", "mini"),
        "Claude 3.5 Sonnet": ("Claude 3.5", ""),
        "Gemini 1.5 Flash": ("Gemini 1.5", "mini"),
        "DeepSeek-V3": ("DeepSeek-V3", ""),
        "Mixtral 8x7B Instruct": ("Mixtral", "instruct"),
        "Qwen3 235B-A22B": ("Qwen3", ""),
        "GPT-4o (2024-05-13 snapshot)": ("GPT-4o", ""),
        "Phi-3-mini-128k-instruct": ("Phi-3", "instruct"),
        "gemma-3-1b-it": ("gemma-3", "instruct"),
        "Command R+": ("Command R", ""),
        "Kimi K2 Thinking": ("Kimi K2", "thinking"),
    }
    for name, expected in cases.items():
        assert family_and_role(name) == expected, (name, family_and_role(name))


def test_curated_models_are_those_with_a_verified_primary_page_event():
    curated = _event("m1", "api_ga", "2025-08-07") | {"confidence": "verified", "source_type": "vendor_blog"}
    inferred_page = _event("m2", "api_ga", "2025-08-07") | {"confidence": "inferred", "source_type": "vendor_blog"}
    machine = _event("m3", "api_ga", "2025-08-07") | {"confidence": "verified", "source_type": "api_metadata"}
    assert curated_model_ids([curated, inferred_page, machine]) == {"m1"}


def test_family_role_recomputed_unless_curated():
    curated = {"model_id": "m1", "canonical_name": "GPT-5.1", "family": "GPT-5", "variant_role": "base"}
    stale = {"model_id": "m2", "canonical_name": "Qwen2.5-72B-Instruct", "family": "old", "variant_role": "other"}
    reviewed = [_event("m1", "api_ga", "2025-08-07") | {"confidence": "verified", "source_type": "vendor_blog", "verified_by": "llm-ledger"}]
    a, b = compute_derived([curated, stale], reviewed)
    assert (a["family"], a["variant_role"]) == ("GPT-5", "base")        # curated stands
    assert (b["family"], b["variant_role"]) == ("Qwen2.5", "instruct")  # machine row re-derived


def test_derived_family_adopts_the_common_spelling():
    rows = [{"model_id": f"q{i}", "canonical_name": n, "family": "", "variant_role": ""}
            for i, n in enumerate(["Qwen3-8B", "Qwen3-32B", "qwen3-coder", "Nameless 7B"])]
    out = compute_derived(rows, [])
    assert [r["family"] for r in out] == ["Qwen3", "Qwen3", "Qwen3", "Nameless"]


def test_year_placeholder_never_sets_the_headline_date():
    events = [_event("m1", "api_ga", "2024-01-01", precision="year")]
    (row,) = compute_derived([_model()], events)
    assert row["first_public_availability_date"] == ""
    assert row["first_availability_via"] == ""
    assert row["first_availability_confidence"] == ""


def test_headline_confidence_follows_the_winning_event():
    events = [_event("m1", "api_ga", "2025-03-01", confidence="verified"),
              _event("m1", "weights_released", "2025-04-01", confidence="inferred")]
    (row,) = compute_derived([_model()], events)
    assert row["first_availability_confidence"] == "verified"
    assert LATEST_COLUMNS.index("first_availability_confidence") == 2


def test_readme_stats_block_is_replaced_in_place():
    from build import README_STATS_END, README_STATS_START, render_readme
    text = f"before\n{README_STATS_START}\nold\n{README_STATS_END}\nafter\n"
    out = render_readme(text, "new stats")
    assert out == f"before\n{README_STATS_START}\nnew stats\n{README_STATS_END}\nafter\n"


def test_machine_row_with_weights_event_becomes_open_weights():
    machine = {"model_id": "m1", "access_type": "api_only", "canonical_name": "M1"}
    curated = {"model_id": "m2", "access_type": "api_only", "canonical_name": "M2"}
    events = [_event("m1", "weights_released", "2025-01-01"),
              _event("m2", "weights_released", "2025-01-01"),
              _event("m2", "announced", "2025-01-01", confidence="verified") | {"source_type": "vendor_blog", "verified_by": "llm-ledger"}]
    a, b = compute_derived([machine, curated], events)
    assert a["access_type"] == "open_weights"
    assert b["access_type"] == "api_only"          # curated rows are a human call


def test_reschedules_chain_each_superseded_claim_to_the_next_statement():
    azure = "https://learn.microsoft.com/azure/retirements"
    events = [{"event_id": "o3-retired-2", "model_id": "o3", "event_type": "retired", "platform": "azure"}]

    def claim(day, superseded_on="", url=azure):
        return {"event_id": "o3-retired-2", "source_url": url, "date": day, "label": "azure_lifecycle (o3)",
                "first_party": "true", "superseded_on": superseded_on}
    claims = [claim("2026-10-01", "2026-09-05"), claim("2026-12-17", "2026-09-12"), claim("2026-11-19"),
              claim("2026-10-01", url="https://raw.githubusercontent.com/x/litellm.json")]
    rows = build_reschedule_rows(events, claims)
    assert [(r["from_date"], r["to_date"], r["days_moved"], r["observed_on"]) for r in rows] == [
        ("2026-10-01", "2026-12-17", "77", "2026-09-05"),
        ("2026-12-17", "2026-11-19", "-28", "2026-09-12"),
    ]
    assert rows[0]["source"] == "azure_lifecycle" and rows[0]["platform"] == "azure"


def test_agent_section_counts_agent_only_models_and_the_last_week_of_declines() -> None:
    agent = {"model_id": "new", "verified_by": "llm-ledger-agent", "source_type": "vendor_blog",
             "confidence": "inferred"}
    machine = {"model_id": "old", "verified_by": "", "source_type": "api_metadata",
               "confidence": "verified"}
    declined = [{"date": "2026-09-20", "reason": "not_a_model", "count": "9"},
                {"date": "2026-09-28", "reason": "not_a_model", "count": "2"},
                {"date": "2026-10-03", "reason": "not_a_model", "count": "1"},
                {"date": "2026-10-03", "reason": "budget", "count": "4"}]
    text = "\n".join(_agent_section([agent, machine], declined))
    assert "single-source inferred 1" in text and "listed yet (withdrawn after 60 days unless one does): 1" in text
    assert "| budget | 4 |" in text and "| not_a_model | 3 |" in text


def test_data_as_of_is_the_newest_pull_that_stored_a_payload() -> None:
    import json
    import tempfile
    saved = schema.RAW_DIR
    schema.RAW_DIR = Path(tempfile.mkdtemp())
    try:
        for day, manifest in (("2026-10-01", {"a.json": {"sha256": "x"}}),
                              ("2026-10-03", {}),                     # the pull failed
                              ("2026-10-02", {"a.json": {"sha256": "y"}})):
            (schema.RAW_DIR / "src" / day).mkdir(parents=True)
            (schema.RAW_DIR / "src" / day / "manifest.json").write_text(json.dumps(manifest))
        assert latest_pull_date() == "2026-10-02"
    finally:
        schema.RAW_DIR = saved


def test_predecessor_leads_follow_family_versions_within_one_name_shape() -> None:
    def model(model_id: str, family: str, day: str, predecessor: str = "") -> dict:
        return {"model_id": model_id, "family": family, "developer_org_id": "zai",
                "first_public_availability_date": day, "predecessor_id": predecessor,
                "successor_id": ""}
    models = [
        model("glm-4-6", "GLM-4.6", "2025-09-30"),
        model("glm-4-7", "GLM-4.7", "2025-12-22"),
        model("glm-5", "GLM-5", "2026-02-11", predecessor="glm-4-5"),
        model("glm-4-6-flash", "GLM-4.6", "2025-10-01"),
        model("glm-4-7-flash", "GLM-4.7", "2025-09-01"),     # dates run backwards
        model("bloomz-1b1", "bloomz-1b1", "2022-10-08"),     # "1b1" is a size
        model("bloomz-1b7", "bloomz-1b7", "2022-10-08"),
    ]
    assert [(r["left_key"], r["right_key"]) for r in predecessor_review_rows(models)] == [
        ("glm-4-7", "glm-4-6")]


def test_capability_joins_by_crosswalk_then_by_undated_name() -> None:
    models = [{c: "" for c in CAPABILITY_COLUMNS[:6]} | {"model_id": mid}
              for mid in ("gpt-4o", "qwen3-32b", "acme-2")]
    crosswalk = [{"model_id": "gpt-4o", "namespace": "epoch", "identifier": "GPT-4o"},
                 {"model_id": "acme-2", "namespace": "epoch", "identifier": "Acme Two"}]

    def entry(name):
        return {"Model": name, "eci": "120", "eci_ci_low": "118", "eci_ci_high": "122",
                "date": "2025-01-01", "Accessibility group": "Closed"}

    rows = capability_rows(models, crosswalk, [entry(n) for n in (
        "GPT-4o", "GPT-4o (Aug 2024)", "Qwen3-32B", "Acme-2", "Unknown 9")], "2026-10-28")
    assert [(r["model_id"], r["matched_by"]) for r in rows] == [
        ("gpt-4o", "crosswalk"), ("qwen3-32b", "name")]
    assert rows[0]["eci_snapshot_date"] == "2026-10-28"


def test_research_views_count_a_paper_once_and_date_from_first_availability() -> None:
    def mention(arxiv_id, version, submitted, model_id, family="Qwen3"):
        return {"arxiv_id": arxiv_id, "version": version, "submitted": submitted,
                "model_id": model_id, "family": family}
    mentions = [mention("1", "v1", "2025-05-02", ""), mention("1", "v1", "2025-05-02", "qwen3-8b"),
                mention("1", "v2", "2025-07-01", "qwen3-8b"), mention("2", "v1", "2025-06-10", "old-1", "Old")]
    assert research_monthly_rows(mentions) == [
        {"month": "2025-05", "family": "Qwen3", "papers": "1"},
        {"month": "2025-06", "family": "Old", "papers": "1"}]
    models = [{"model_id": mid, "canonical_name": mid, "family": fam, "access_type": "open_weights",
               "first_public_availability_date": day}
              for mid, fam, day in (("qwen3-8b", "Qwen3", "2025-04-29"), ("old-1", "Old", "2022-01-01"),
                                    ("unnamed", "X", "2025-01-01"))]
    events = [_event("qwen3-8b", "weights_released", "2025-04-29")]
    rows = first_mention_rows(models, events, mentions, harvested_from="2023-01-01")
    assert [(r["model_id"], r["first_mention"], r["days_to_first_mention"], r["weights_released_date"])
            for r in rows] == [("old-1", "2025-06-10", "", ""), ("qwen3-8b", "2025-05-02", "3", "2025-04-29")]


def test_every_bundle_exports_existing_tables_with_ledger_ids() -> None:
    model_ids = {m["model_id"] for m in schema.read_table(MODELS)}
    for name, (tables, event_types) in bundles.BUNDLES.items():
        assert event_types <= schema.EVENT_TYPES, name
        assert all((schema.REPO_ROOT / p).exists() for p in bundles.IDENTITY + tables), name
    with tempfile.TemporaryDirectory() as tmp:
        path = bundles.write_bundle("governance", Path(tmp))
        with zipfile.ZipFile(path) as zf:
            names = {n.split("/", 1)[1] for n in zf.namelist()}
            events = zf.read("llm-ledger-governance/events.csv").decode().splitlines()[1:]
    assert {"models.csv", "organizations.csv", "events.csv", "claims.csv", "METHODS.md",
            "LICENSE", "reschedules.csv"} == names
    assert events and all(line.split(",")[1] in model_ids for line in events)
