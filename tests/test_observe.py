"""observe: daily listings fold into runs; ids resolve through the crosswalk."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import observe
import pull_research_mentions as research
import schema

PRICE = schema.PRICE_OBSERVATIONS


def _price(price_input: str) -> dict:
    return {"source": "openrouter", "provider": "openrouter", "api_id": "acme/acme-1",
            "price_input": price_input, "price_output": "0.00001", "price_cached": "",
            "currency": "USD", "unit": "per_token", "source_url": "https://openrouter.ai/api/v1/models"}


def test_a_run_grows_while_values_hold_and_breaks_on_a_change_or_a_missed_day() -> None:
    rows: list = []
    assert observe.extend_runs(rows, [_price("0.000002")], PRICE, date(2026, 10, 1)) == 1
    assert observe.extend_runs(rows, [_price("0.000002")], PRICE, date(2026, 10, 2)) == 0
    assert observe.extend_runs(rows, [_price("0.000001")], PRICE, date(2026, 10, 3)) == 1
    # No pull on 10-04: the same price on 10-05 is a new run, not a continuation.
    assert observe.extend_runs(rows, [_price("0.000001")], PRICE, date(2026, 10, 5)) == 1
    assert [(r["price_input"], r["first_observed"], r["last_observed"]) for r in rows] == [
        ("0.000002", "2026-10-01", "2026-10-02"),
        ("0.000001", "2026-10-03", "2026-10-03"),
        ("0.000001", "2026-10-05", "2026-10-05")]
    try:
        observe.extend_runs(rows, [_price("0.1"), _price("0.2")], PRICE, date(2026, 10, 6))
    except ValueError:
        pass
    else:
        raise AssertionError("one id at two prices on one day must fail")


def test_resolver_prefers_the_exact_identifier_and_refuses_an_ambiguous_key() -> None:
    crosswalk = [
        {"model_id": "acme-1", "namespace": "models_dev", "identifier": "acme/acme-1"},
        {"model_id": "acme-1-0901", "namespace": "openrouter", "identifier": "acme/acme-1-0901"},
        {"model_id": "acme-2", "namespace": "models_dev", "identifier": "acme/acme-2"},
        {"model_id": "acme-2-pro", "namespace": "openrouter", "identifier": "acme/acme-2"},
    ]
    resolve = observe.model_resolver(crosswalk)
    assert resolve("models_dev", "acme", "acme-1") == "acme-1"
    assert resolve("models_dev", "reseller", "acme/acme-1") == "acme-1"      # key fallback
    assert resolve("models_dev", "reseller", "acme-1-0901") == "acme-1-0901"  # snapshot kept apart
    assert resolve("openrouter", "openrouter", "acme/acme-2") == "acme-2-pro"
    assert resolve("models_dev", "reseller", "acme-2") == ""                  # two models share the key


def test_versions_backfill_days_the_other_tables_already_hold() -> None:
    import json
    import tempfile
    root = Path(tempfile.mkdtemp())
    vendor_header = "id,created_date,shutdown_date,display_name,max_input_tokens,max_output_tokens,aliases\n"
    for day in ("2026-10-01", "2026-10-02"):
        d = root / "openai_api" / day
        d.mkdir(parents=True)
        (d / "normalized.csv").write_text(vendor_header + "acme-1,2025-01-01,,,,,\n"
                                          "acme-1-2025-06-01,2025-06-01,,,,,\n")
        (d / "manifest.json").write_text(json.dumps(
            {"models.json": {"url": "https://api.openai.com/v1/models", "sha256": "x"}}))
        h = root / "hf" / day
        h.mkdir(parents=True)
        sha = "" if day == "2026-10-01" else ",sha,last_modified"
        rows = "acme/acme-1,acme,acme,2025-01-01,1,text-generation,mit,"
        (h / "normalized.csv").write_text(
            "repo_id,namespace,org_id,created_at,downloads,pipeline_tag,license,tags" + sha + "\n"
            + rows + (",abc123,2026-09-30" if sha else "") + "\n")
        (h / "manifest.json").write_text(json.dumps(
            {"normalized.csv": {"url": "https://huggingface.co/api/models", "sha256": "y"}}))
    tables = {t.name: [] for t in schema.OBSERVATION_TABLES}
    crosswalk = [{"model_id": "acme-1", "namespace": "openai_api", "identifier": "acme-1"},
                 {"model_id": "acme-1", "namespace": "huggingface", "identifier": "acme/acme-1"}]
    observe.observe(root, tables, crosswalk)
    tables[schema.MODEL_VERSIONS.name].clear()
    before = [dict(r) for r in tables[schema.AVAILABILITY_OBSERVATIONS.name]]
    observe.observe(root, tables, crosswalk)
    assert tables[schema.AVAILABILITY_OBSERVATIONS.name] == before
    versions = {(r["source"], r["api_id"]): (r["version_id"], r["stated_date"], r["model_id"],
                                             r["first_observed"], r["last_observed"])
                for r in tables[schema.MODEL_VERSIONS.name]}
    # Only the dated id is a snapshot; the sweep without `sha` adds nothing.
    assert versions == {
        ("openai_api", "acme-1-2025-06-01"): ("acme-1-2025-06-01", "2025-06-01", "",
                                              "2026-10-01", "2026-10-02"),
        ("hf", "acme/acme-1"): ("abc123", "2026-09-30", "acme-1", "2026-10-02", "2026-10-02")}


def test_market_prices_convert_to_per_million_and_drop_the_router_marker() -> None:
    import market
    assert market.per_1m("2.5e-06", "per_token") == "2.5"
    assert market.per_1m("0.00001", "per_token") == "10"
    assert market.per_1m("0.3", "per_1m_tokens") == "0.3"
    assert market.per_1m("-1", "per_token") == ""
    assert market.per_1m("", "per_token") == ""


def test_price_changes_skip_missed_pull_breaks_and_mark_the_makers_own_price() -> None:
    import market

    def run(provider: str, price_input: str, first: str, last: str) -> dict:
        return {"model_id": "gpt-x", "source": "models_dev", "provider": provider,
                "api_id": "gpt-x", "price_input": price_input, "price_output": "8",
                "price_cached": "", "unit": "per_1m_tokens", "first_observed": first,
                "last_observed": last, "source_url": "https://models.dev/api.json"}
    observations = {schema.PRICE_OBSERVATIONS.name: [
        run("openai", "2", "2026-10-01", "2026-10-03"),
        run("openai", "2", "2026-10-05", "2026-10-06"),        # missed pull on 10-04
        run("openai", "1.5", "2026-10-07", "2026-10-09"),
        run("azure-openai", "2", "2026-10-01", "2026-10-02"),
        run("azure-openai", "2.2", "2026-10-03", "2026-10-09"),
    ]}
    models = [{"model_id": "gpt-x", "developer_org_id": "openai"}]
    rows = market.price_change_rows(models, observations)
    assert [(r["provider"], r["first_party"], r["last_old_day"], r["first_new_day"],
             r["input_old"], r["input_new"]) for r in rows] == [
        ("azure-openai", "false", "2026-10-02", "2026-10-03", "2", "2.2"),
        ("openai", "true", "2026-10-06", "2026-10-07", "2", "1.5")]


def _research_index() -> dict:
    models = [{"model_id": mid, "canonical_name": name, "family": family}
              for mid, name, family in (("gpt-4o", "GPT-4o", "GPT-4o"),
                                        ("gpt-4o-mini", "GPT-4o mini", "GPT-4o"),
                                        ("qwen2-5-7b", "Qwen2.5 7B", "Qwen2.5"),
                                        ("qwen2-5-72b", "Qwen2.5 72B", "Qwen2.5"),
                                        ("qwen2-5-14b", "Qwen2.5 14B", "Qwen 2.5"))]
    crosswalk = [{"model_id": "qwen2-5-72b", "namespace": "text_surface_forms", "identifier": "Qwen2.5"},
                 {"model_id": "qwen2-5-72b", "namespace": "text_surface_forms", "identifier": "Qwen"},
                 {"model_id": "qwen2-5-7b", "namespace": "huggingface", "identifier": "Qwen/Qwen2.5-7B-Instruct"}]
    return research.form_index(models, crosswalk)


def test_research_mentions_take_the_longest_spelling_and_keep_families_unattributed() -> None:
    text = "We fine-tune Qwen2.5-7B-Instruct and Qwen 2.5, compare GPT-4o-mini to GPT-4o and Qwen."
    index = _research_index()
    found = {(mid, fam): m for mid, fam, m in research.mentions(text, index)}
    assert found == {("qwen2-5-7b", "Qwen2.5"): "Qwen2.5-7B-Instruct", ("", "Qwen2.5"): "Qwen 2.5",
                     ("gpt-4o-mini", "GPT-4o"): "GPT-4o-mini", ("gpt-4o", "GPT-4o"): "GPT-4o"}
    assert research.mentions("served as qwen2.5:7b", index) == [("qwen2-5-7b", "Qwen2.5", "qwen2.5:7b")]
    assert research.mentions("the Qwen, 2.5 and qwen 2.5 cases; GPT^{4o}", index) == []


def test_research_pages_read_the_latest_version_and_skip_deleted_records() -> None:
    oai, raw = "http://www.openarchives.org/OAI/2.0/", "http://arxiv.org/OAI/arXivRaw/"
    page = (f'<OAI-PMH xmlns="{oai}"><ListRecords>'
            '<record><header status="deleted"><identifier>x</identifier></header></record>'
            f'<record><header><identifier>y</identifier></header><metadata><arXivRaw xmlns="{raw}">'
            '<id>2401.00001</id><version version="v1"><date>Mon, 1 Jan 2024 10:00:00 GMT</date></version>'
            '<version version="v2"><date>Tue, 5 Mar 2024 23:30:00 GMT</date></version>'
            '<title>A\n  title</title><abstract>An abstract.</abstract></arXivRaw></metadata></record>'
            '<resumptionToken>next</resumptionToken></ListRecords></OAI-PMH>').encode()
    assert research.parse_page(page) == (
        [("2401.00001", "v2", "2024-03-05", "A title", "An abstract.")], "next")
    empty = f'<OAI-PMH xmlns="{oai}"><error code="noRecordsMatch">none</error></OAI-PMH>'.encode()
    assert research.parse_page(empty) == ([], "")


def test_research_merge_replaces_reread_versions_only() -> None:
    def row(arxiv_id, version, model_id):
        return {"arxiv_id": arxiv_id, "version": version, "model_id": model_id, "family": "F"}
    existing = [row("1", "v1", "a"), row("1", "v2", "a"), row("2", "v1", "gone")]
    merged = research.merge(existing, [row("1", "v2", "b")], {("1", "v2")}, {"a", "b"})
    assert merged == [row("1", "v1", "a"), row("1", "v2", "b")]
    assert research._windows(date(2025, 12, 20), date(2026, 2, 3)) == [
        (date(2025, 12, 20), date(2025, 12, 31)), (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 3))]
