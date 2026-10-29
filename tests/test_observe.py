"""observe: daily listings fold into runs; ids resolve through the crosswalk."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
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


def test_litellm_history_carries_a_commit_forward_and_breaks_the_run_on_a_price_change() -> None:
    """LiteLLM's GPT-4o entry as it stood on 2024-11-11..13: one commit
    covers the first two days, the next one cuts the price."""
    import gzip
    import json
    import tempfile
    import pull_litellm_history as history
    old, new = "f59cb46e71401698ae5e40e8277223a76c4905e3", "e7543378b8b7c6ebb08afe28db64700a7b5232d7"
    by_day = history.commits_by_day(f"{old} 2024-11-11T13:46:35-05:00\n"
                                    f"{new} 2024-11-12T21:40:52-05:00\n")
    days = history.day_commits(by_day, date(2024, 11, 13))
    assert [(d.isoformat(), c) for d, c, _ in days] == [
        ("2024-11-11", old), ("2024-11-12", old), ("2024-11-13", new)]  # 21:40 EST is 11-13 UTC
    try:
        history.commits_by_day(f"{new} 2024-11-13T02:40:52Z\n{old} 2024-11-11T18:46:35Z\n")
    except ValueError:
        pass
    else:
        raise AssertionError("a commit dated before its first parent must fail")

    payloads = {old: '{"gpt-4o": {"input_cost_per_token": 0.000005, "output_cost_per_token": '
                     '0.000015, "litellm_provider": "openai", "max_input_tokens": 128000}}',
                new: '{"gpt-4o": {"input_cost_per_token": 0.0000025, "output_cost_per_token": '
                     '0.000010, "litellm_provider": "openai", "max_input_tokens": 128000}}'}
    root = Path(tempfile.mkdtemp())
    for day, commit, _ in days:
        d = root / "litellm_git" / day.isoformat()
        d.mkdir(parents=True)
        (d / "model_prices_and_context_window.json.gz").write_bytes(
            gzip.compress(payloads[commit].encode()))
        (d / "manifest.json").write_text(json.dumps({"model_prices_and_context_window.json": {
            "url": history.RAW_URL.format(commit=commit), "sha256": "x"}}))
    tables = {t.name: [] for t in schema.OBSERVATION_TABLES}
    crosswalk = [{"model_id": "gpt-4o", "namespace": "openrouter", "identifier": "openai/gpt-4o"}]
    observe.observe(root, tables, crosswalk)
    assert [(r["source"], r["model_id"], r["price_input"], r["first_observed"], r["last_observed"],
             r["source_url"].split("/")[5]) for r in tables[PRICE.name]] == [
        ("litellm_git", "gpt-4o", "0.000005", "2024-11-11", "2024-11-12", old),
        ("litellm_git", "gpt-4o", "0.0000025", "2024-11-13", "2024-11-13", new)]
    # The limit did not change, so its run spans all three days from the first commit.
    assert [(r["context_length"], r["first_observed"], r["last_observed"])
            for r in tables[schema.CAPABILITY_OBSERVATIONS.name]] == [
        ("128000", "2024-11-11", "2024-11-13")]


def test_downloads_keep_ledger_repos_and_meet_the_modelscope_twin_by_org_and_name() -> None:
    """Yi-1.5-34B-Chat in hub-stats on 2024-07-29 and on ModelScope (as
    01ai/, not 01-ai/) on 2026-10-27; an unmapped repo is dropped."""
    import json
    import tempfile
    import pull_hub_stats
    root = Path(tempfile.mkdtemp())
    payloads = {
        ("hub_stats", "2024-07-29", "models.parquet"):
            "repo_id,downloads,downloads_all_time\n01-ai/Yi-1.5-34B-Chat,11061,\nsomeone/else,5,\n",
        ("modelscope", "2026-10-27", "normalized.csv"):
            "repo_id,namespace,org_id,created_at,last_updated,downloads,task,license\n"
            "01ai/Yi-1.5-34B-Chat,01ai,01ai,2024-05-12,2024-06-27,20950,text-generation,apache\n"
            "01ai/Yi-9Z,01ai,01ai,2024-05-12,2024-06-27,,text-generation,apache\n"}
    for (source, day, manifest_key), text in payloads.items():
        d = root / source / day
        d.mkdir(parents=True)
        (d / "normalized.csv").write_text(text)
        (d / "manifest.json").write_text(json.dumps({manifest_key: {"url": "u", "sha256": "x"}}))
    tables = {t.name: [] for t in schema.OBSERVATION_TABLES}
    crosswalk = [{"model_id": "yi-1-5-34b-chat", "namespace": "huggingface",
                  "identifier": "01-ai/Yi-1.5-34B-Chat"}]
    observe.observe(root, tables, crosswalk, {"yi-1-5-34b-chat": "01ai"})
    assert [(r["source"], r["api_id"], r["model_id"], r["downloads_30d"], r["downloads_all_time"],
             r["first_observed"]) for r in tables[schema.DOWNLOAD_OBSERVATIONS.name]] == [
        ("hub_stats", "01-ai/Yi-1.5-34B-Chat", "yi-1-5-34b-chat", "11061", "", "2024-07-29"),
        ("modelscope", "01ai/Yi-1.5-34B-Chat", "yi-1-5-34b-chat", "", "20950", "2026-10-27")]

    when = datetime(2024, 7, 29, 22, 3, tzinfo=timezone.utc)
    commits = [("b", when + timedelta(days=1), "Upload models.parquet with huggingface_hub"),
               ("a", when, "Upload models.parquet with huggingface_hub"),
               ("c", when, "Upload spaces.parquet with huggingface_hub"),
               ("d", when + timedelta(days=7), "Upload models.parquet with huggingface_hub")]
    assert [(d.isoformat(), rev) for d, rev, _ in pull_hub_stats.weekly_uploads(commits)] == [
        ("2024-07-29", "a"), ("2024-08-05", "d")]


def test_descendants_count_direct_children_of_ledger_repos_by_relation() -> None:
    """baseModels of real repos in hub-stats' models.parquet (2026-10): two
    GGUFs of DeepSeek-V4.1-Flash-1017, a Qwen3-14B fine-tune, a merge with
    gemma-4-26B-A4B-it among its bases (4 of its 12 kept), and a repo
    naming no base."""
    import pull_hub_stats
    flash, qwen, gemma = ("deepseek-ai/DeepSeek-V4.1-Flash-1017", "Qwen/Qwen3-14B",
                          "google/gemma-4-26B-A4B-it")
    merge_bases = ["ConicCat/Gemma4-Writer-26BA4B", "Naphula/Goetia-26B-A4B-v1.6",
                   "TheDrummer/Orion-26B-A4B-v1.1", gemma]
    entries = [{"relation": "quantized", "models": [{"id": flash}]},  # ISTA-DASLab ...-GSQ-RCO-GGUF
               {"relation": "quantized", "models": [{"id": flash}]},  # orcarouter ...-abliterated-GGUF
               {"relation": "finetune", "models": [{"id": qwen}]},  # HuggingFaceBio/Carbon-X
               {"relation": "merge", "models": [{"id": b} for b in merge_bases]},  # Naphula/Goetia-26B-A4B-v1.7
               None]
    assert pull_hub_stats.descendant_counts(entries, {flash, qwen, gemma}) == [
        {"repo_id": qwen, "relation": "finetune", "descendants": "1"},
        {"repo_id": flash, "relation": "quantized", "descendants": "2"},
        {"repo_id": gemma, "relation": "merge", "descendants": "1"}]


def test_openrouter_ranking_keeps_exact_tokens_and_a_day_total_that_includes_other() -> None:
    """Four of OpenRouter's rows for 2025-01-01 (the day cut to them)."""
    import pull_openrouter_rankings as rankings
    assert rankings.spans(date(2025, 1, 1), date(2026, 10, 28)) == [
        (date(2025, 1, 1), date(2026, 1, 1)), (date(2026, 1, 2), date(2026, 10, 28))]
    payload = {"meta": {"as_of": "2026-10-29T03:59:11.480Z"}, "data": [
        {"date": "2025-01-01", "model_permaslug": "anthropic/claude-3.5-sonnet:beta",
         "total_tokens": "11646035656"},
        {"date": "2025-01-01", "model_permaslug": "anthropic/claude-3.5-sonnet",
         "total_tokens": "7543940725"},
        {"date": "2025-01-01", "model_permaslug": "deepseek/deepseek-chat-v3-20241226",
         "total_tokens": "4206734934"},
        {"date": "2025-01-01", "model_permaslug": "other", "total_tokens": "2241676199"}]}
    slug_ids = rankings.permaslug_ids([[
        {"id": "deepseek/deepseek-chat", "canonical_slug": "deepseek/deepseek-chat-v3-20241226"},
        {"id": "deepseek/deepseek-chat:free", "canonical_slug": "deepseek/deepseek-chat-v3-20241226"}]])
    resolve = observe.model_resolver([
        {"model_id": "claude-3-5-sonnet", "namespace": "openrouter",
         "identifier": "anthropic/claude-3.5-sonnet"},
        {"model_id": "deepseek-v3", "namespace": "openrouter", "identifier": "deepseek/deepseek-chat"}])
    rows = rankings.usage_rows(payload, "u", resolve, slug_ids)
    assert [(r["model_permaslug"].split("/")[-1], r["model_id"], r["rank"]) for r in rows] == [
        ("claude-3.5-sonnet:beta", "claude-3-5-sonnet", "1"), ("claude-3.5-sonnet", "claude-3-5-sonnet", "2"),
        ("deepseek-chat-v3-20241226", "deepseek-v3", "3"), ("other", "", "")]
    assert {r["day_total_tokens"] for r in rows} == {
        str(sum(int(r["total_tokens"]) for r in payload["data"]))}
    payload["data"][0]["total_tokens"] = "1.2e10"
    try:
        rankings.usage_rows(payload, "u", resolve, slug_ids)
    except ValueError:
        pass
    else:
        raise AssertionError("a token count that is not a whole number must fail")


def test_citations_take_the_first_paper_link_and_copy_both_sources_counts() -> None:
    """DeepSeek-R1's report (2501.12948) as OpenAlex and Semantic Scholar
    stated it on 2026-10-29."""
    import pull_citations as citations
    events = [{"model_id": "deepseek-r1", "event_type": "paper_published",
               "source_url": "https://arxiv.org/abs/2501.12948"}]
    crosswalk = [
        {"model_id": "deepseek-r1", "namespace": "epoch", "identifier": "DeepSeek-R1"},
        {"model_id": "deepseek-r1-distill-qwen-7b", "namespace": "epoch", "identifier": "R1 Distill"},
        {"model_id": "yi-34b", "namespace": "huggingface", "identifier": "01-ai/Yi-34B"},
        {"model_id": "many", "namespace": "huggingface", "identifier": "x/many"}]
    epoch = {"DeepSeek-R1": "https://arxiv.org/abs/9999.00001",   # the event wins over Epoch
             "R1 Distill": "https://arxiv.org/abs/2501.12948"}
    tags = {"01-ai/Yi-34B": "transformers|arxiv:2403.04652|license:other",
            "x/many": "arxiv:2401.00001|arxiv:2401.00002"}          # several papers: left out
    papers = citations.model_papers(events, crosswalk, epoch, tags)
    assert papers == [("deepseek-r1", "2501.12948", "paper_published_event"),
                      ("deepseek-r1-distill-qwen-7b", "2501.12948", "epoch_link"),
                      ("yi-34b", "2403.04652", "hf_card_arxiv_tag")]
    openalex = [{"id": "https://openalex.org/W4406779522", "doi": "https://doi.org/10.48550/arxiv.2501.12948",
                 "cited_by_count": 540, "counts_by_year": [{"year": 2026, "cited_by_count": 132},
                                                           {"year": 2025, "cited_by_count": 407}]}]
    s2 = [{"paperId": "2eed1fad9bbf887d4395de40f20144c4fafefd7f", "citationCount": 5954,
           "externalIds": {"ArXiv": "2501.12948", "DOI": "10.1038/s41586-025-09422-z"}}]
    rows, links = citations.citation_rows(papers[:1], openalex, s2, "2026-10-29")
    assert [(r["source"], r["year"], r["citations"]) for r in rows] == [
        ("openalex", "", "540"), ("openalex", "2026", "132"), ("openalex", "2025", "407"),
        ("semantic_scholar", "", "5954")]
    assert [(link["namespace"], link["identifier"]) for link in links] == [
        ("openalex", "W4406779522"), ("semantic_scholar", "2eed1fad9bbf887d4395de40f20144c4fafefd7f")]


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
