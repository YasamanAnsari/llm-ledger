"""Matcher normalization tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from match import key_variants, normalize_name


def test_stated_release_prefers_vendor_then_majority_then_refuses_to_guess():
    from match import open_weights_vote, stated_release
    assert stated_release([("openai", "2025-04-16"), ("poe", "2025-04-20")], "openai") == ("2025-04-16", "first_party")
    assert stated_release([("poe", "2025-11-18"), ("venice", "2025-11-18"), ("x", "2025-10-22")], "anthropic") == ("2025-11-18", "majority")
    assert stated_release([("poe", "2024-06-20"), ("venice", "2025-09-09"), ("x", "2024-10-22")], "anthropic") == ("", "")
    assert stated_release([("poe", "2025-10-22"), ("venice", "2025-11-18")], "google") == ("", "")
    assert stated_release([("sap-ai-core", "2025-12-02")], "amazon") == ("2025-12-02", "single")
    assert stated_release([("poe", ""), ("venice", "1970-01-01")], "x") == ("", "")
    assert open_weights_vote([("deepseek", "false"), ("a", "true"), ("b", "true")], "deepseek") is False
    assert open_weights_vote([("a", "true"), ("b", "true"), ("c", "false")], "zhipu") is True
    assert open_weights_vote([("a", "true"), ("b", "false")], "mistral") is False


def test_prefix_and_separators():
    n = normalize_name("openai/GPT-4.1 Mini")
    assert n["prefix"] == "openai", n
    assert n["key"] == "gpt-4-1-mini", n


def test_openrouter_serving_variant_stripped():
    n = normalize_name("z-ai/glm-4.5:free")
    assert n["key"] == "glm-4-5", n
    assert n["prefix"] == "z-ai", n


def test_date_suffix_becomes_snapshot():
    for raw, expected_key, expected_suffix in (
        ("gpt-4o-2024-05-13", "gpt-4o", "2024-05-13"),
        ("openai/gpt-5.2-20251211", "gpt-5-2", "20251211"),
        ("gpt-4-0613", "gpt-4", "0613"),
        ("deepseek-v3-0324", "deepseek-v3", "0324"),
    ):
        n = normalize_name(raw)
        assert n["key"] == expected_key, (raw, n)
        assert n["snapshot_suffix"] == expected_suffix, (raw, n)


def test_size_suffix_not_mistaken_for_date():
    n = normalize_name("01-ai/Yi-34B")
    assert n["key"] == "yi-34b", n
    assert n["snapshot_suffix"] == "", n


def test_org_noise_prefix_rewritten():
    assert normalize_name("meta-llama/Meta-Llama-3-70B-Instruct")["key"] == "llama-3-70b-instruct"
    assert normalize_name("venice/google-gemma-3-27b-it")["key"] == "gemma-3-27b-it"
    assert normalize_name("deepseek-ai/DeepSeek-R1")["key"] == "deepseek-r1"


def test_epoch_display_names():
    assert normalize_name("GPT-4o")["key"] == "gpt-4o"
    assert normalize_name("Llama 3.1-405B")["key"] == "llama-3-1-405b"
    assert normalize_name("Claude 3.5 Sonnet")["key"] == "claude-3-5-sonnet"


def test_key_variants_strip_serving_format():
    variants = key_variants("qwen2-5-72b-instruct")
    assert variants[0] == "qwen2-5-72b-instruct"
    assert "qwen2-5-72b" in variants
    assert key_variants("gpt-4o")[0] == "gpt-4o"


def test_key_variants_bridge_letter_digit_boundary():
    # vendor spelling (fused) and aggregator spelling (split) must reach
    # each other, in both directions
    assert "qwen2-5-72b-instruct" in key_variants("qwen-2-5-72b-instruct")
    assert "qwen-2-5-72b-instruct" in key_variants("qwen2-5-72b-instruct")
    assert "lfm2-5-2-6b" in key_variants("lfm-2-5-2-6b")


def test_slug_for_prefixes_short_keys():
    from match import slug_for
    assert slug_for("o3", "openai") == "openai-o3"
    assert slug_for("hy3", "tencent") == "tencent-hy3"
    assert slug_for("gpt-4o", "openai") == "gpt-4o"
    assert slug_for("r1", "deepseek") == "deepseek-r1"


def test_format_suffix_is_stripped_and_recorded():
    for raw, key, fmt in (
        ("zai-org/GLM-5.3-BF16", "glm-5-3", "bf16"),
        ("tencent/Hy4-preview-FP8", "hy4-preview", "fp8"),
        ("baidu/ERNIE-4.5-300B-A47B-FP8-Paddle", "ernie-4-5-300b-a47b", "fp8-paddle"),
        ("meta-llama/Llama-3.1-405B-Instruct-FP8", "llama-3-1-405b-instruct", "fp8"),
        ("meta-llama/Llama-2-70b-chat-hf", "llama-2-70b-chat", "hf"),
        ("inclusionAI/Ling-3.0-flash-int4", "ling-3-0-flash", "int4"),
        ("01-ai/Yi-34B", "yi-34b", ""),
        ("Qwen/Qwen3-235B-A22B", "qwen3-235b-a22b", ""),
    ):
        n = normalize_name(raw)
        assert (n["key"], n["format_suffix"]) == (key, fmt), (raw, n)


def test_alias_and_out_of_scope_keys():
    from match import is_alias_key, is_out_of_scope_key
    for alias in ("claude-sonnet-latest", "gpt-chat-latest", "deepseek-chat", "gemini-exp", "kimi-latest"):
        assert is_alias_key(alias), alias
    for real in ("deepseek-v3-2-exp", "hy4-preview", "gemini-2-5-pro-preview", "baichuan-13b-chat"):
        assert not is_alias_key(real), real
    for out in ("text-embedding-3-large", "codestral-embed", "gemini-embedding", "esm2-650m",
                "visionreward-video", "gpt-4o-transcribe", "rerank-v3-5", "omni-moderation",
                "gpt-image-2", "gemini-2-5-flash-image", "veo3-1", "imagen-3", "qwen-image", "lyria"):
        assert is_out_of_scope_key(out), out
    for kept in ("llama-3-2-11b-vision", "voxtral-small", "gpt-audio", "qwen2-5-vl-72b", "llama-guard-3-8b",
                 "gpt-5-5-pro", "gemini-3-pro"):
        assert not is_out_of_scope_key(kept), kept


def test_identity_variants_keep_the_role():
    assert "qwen2-5-72b" not in key_variants("qwen2-5-72b-instruct", identity=True)
    assert "qwen-2-5-72b-instruct" in key_variants("qwen2-5-72b-instruct", identity=True)
    assert "qwen2-5-72b" in key_variants("qwen2-5-72b-instruct")   # cross-catalog matching only


def test_review_decisions_settle_fuzzy_pairs():
    from match import apply_fuzzy_decision
    decisions = {("fuzzy_match", "deepseekmath-v2", "deepseek-math-v2"): {"decision": "accept"},
                 ("fuzzy_match", "gemini-1-5-flash", "gemini-2-5-flash"): {"decision": "reject"}}
    assert apply_fuzzy_decision(decisions, "deepseekmath-v2", "deepseek-math-v2") == "accept"
    assert apply_fuzzy_decision(decisions, "gemini-1-5-flash", "gemini-2-5-flash") == "reject"
    assert apply_fuzzy_decision(decisions, "a", "b") == ""


def _md(key, provider, model_key, release):
    norm = normalize_name(f"{provider}/{model_key}")
    row = {"provider": provider, "model_key": model_key, "release_date": release,
           "open_weights": "true", "modalities_in": "text", "modalities_out": "text",
           "context_length": "", "max_output_tokens": "", "cost_input": "", "cost_output": "",
           "cost_cache_read": "", "reasoning": "", "tool_call": "", "knowledge_cutoff": ""}
    return {key: {"norm": norm, "row": row, "release_date": release, "provider_count": 1,
                  "dates": [(provider, release)], "ow_votes": [(provider, "true")]}}


def _or(key, or_id, created):
    return {key: {"norm": normalize_name(or_id),
                  "row": {"id": or_id, "created_date": created, "expiration_date": ""}}}


def _epoch(key, name, org, published):
    return {key: {"norm": normalize_name(name),
                  "row": {"model": name, "organization": org, "publication_date": published,
                          "confidence": ""}}}


def test_match_clusters_by_identity_variants_and_never_auto_accepts_below_97():
    from match import match
    md = _md("qwen2-5-72b-instruct", "alibaba", "qwen2.5-72b-instruct", "2024-09-19")
    orr = _or("qwen-2-5-72b-instruct", "qwen/qwen-2.5-72b-instruct", "2024-09-19")
    epoch = _epoch("gemini-1-5-flash", "Gemini 1.5 Flash", "Google", "2024-05-14")
    rows, queue = match(md, orr, epoch, md_snapshot="2026-09-01")
    (cluster,) = [r for r in rows if r["match_key"] == "qwen2-5-72b-instruct"]
    assert cluster["sources"] == "models_dev|openrouter" and "or:exact" in cluster["match_method"]
    assert cluster["md_snapshot_date"] == "2026-09-01"
    assert not any("fuzzy" in r["match_method"] for r in rows)
    assert len(rows) == 1  # an Epoch entry alone never seeds a cluster


def test_match_applies_review_decisions_to_the_fuzzy_band():
    from match import match
    # 92-97 band pair: queued without a decision, joined once accepted,
    # silently dropped once rejected.
    md = _md("deepseek-math-v2", "deepseek", "deepseek-math-v2", "2025-11-27")
    orr = _or("deepseekmath-v2", "deepseek/deepseekmath-v2", "2025-11-28")
    rows, queue = match(md, orr, {})
    assert [(q["left_key"], q["right_key"]) for q in queue] == [("deepseekmath-v2", "deepseek-math-v2")]
    assert {r["sources"] for r in rows} == {"models_dev", "openrouter"}

    accept = {("fuzzy_match", "deepseekmath-v2", "deepseek-math-v2"): {"decision": "accept"}}
    rows, queue = match(md, orr, {}, decisions=accept)
    (cluster,) = rows
    assert cluster["sources"] == "models_dev|openrouter" and cluster["match_method"] == "or:reviewed"
    assert queue == []

    reject = {("fuzzy_match", "deepseekmath-v2", "deepseek-math-v2"): {"decision": "reject"}}
    rows, queue = match(md, orr, {}, decisions=reject)
    assert {r["sources"] for r in rows} == {"models_dev", "openrouter"} and queue == []
