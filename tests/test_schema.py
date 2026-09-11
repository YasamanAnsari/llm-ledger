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
