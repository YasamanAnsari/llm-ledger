"""Schema helper tests."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from schema import license_family


def test_license_family_does_not_guess():
    assert license_family("apache-2.0") == "osi_approved"
    assert license_family("Apache 2.0") == "osi_approved"
    assert license_family("MIT") == "osi_approved"
    assert license_family("openrail") == "open_weights_restricted"   # not OSI-approved
    assert license_family("llama3.1") == "open_weights_restricted"
    assert license_family("cc-by-nc-4.0") == "open_weights_restricted"
    assert license_family("proprietary") == "proprietary"
    for unknown in ("", "other", "unknown"):
        assert license_family(unknown) == ""


def test_foreign_family_and_classification():
    import orgs_seed
    from hf_census import classify
    assert orgs_seed.foreign_family("llama-3-1-70b", "nous-research") == (0, "meta")
    assert orgs_seed.foreign_family("hermes-3-llama-3-1-8b", "nous-research") == (2, "meta")
    assert orgs_seed.foreign_family("gpt-neox-20b", "eleutherai") == (-1, "")   # gpt is not a foreign token
    assert orgs_seed.foreign_family("qwen2-5-72b-instruct", "alibaba") == (-1, "")
    assert classify("llama-3-1-70b", "nous-research") == "mirror"
    assert classify("hermes-3-llama-3-1-8b", "nous-research") == "derivative"
    assert classify("deephermes-3-llama-3-8b-preview", "nous-research") == "derivative"
    assert classify("llama-3-1-nemotron-70b-instruct", "nvidia") == "derivative"
    assert classify("llama-3-1-tulu-3-8b", "allenai") == "derivative"
    assert classify("minicpm-llama3-v-2-5", "openbmb") == "derivative"
    assert classify("deepseek-r1-distill-llama-8b", "deepseek") == "derivative"
    assert classify("gpt-neox-20b", "eleutherai") == "own"
    assert classify("llama-3-1-70b", "meta") == "own"
    from schema import derivative_from_name
    assert derivative_from_name("deepseek-r1-distill-llama-8b", "deepseek") == "distill"
    assert derivative_from_name("hermes-3-llama-3-1-8b", "nous-research") == "finetune"
    assert derivative_from_name("qwen2-5-72b-instruct", "alibaba") == ""
