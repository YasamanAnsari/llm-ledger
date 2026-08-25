"""Matcher normalization tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from match import key_variants, normalize_name


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
