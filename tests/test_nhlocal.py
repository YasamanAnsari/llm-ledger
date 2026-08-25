"""Tests for the NHLOCAL timeline line parser."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from pull_nhlocal import parse_timeline

SAMPLE = """\
- year: 2022
  events:
  - date: November
    info:
    - text: <b>ChatGPT</b>, a chatbot by OpenAI, is released.
      special: true
    - text: <b>Midjourney v4</b> is released.
- year: 2023
  events:
  - date: March
    info:
    - text: OpenAI announces <b>GPT-4</b> and <b>GPT-4 API</b>.
"""


def test_parse_timeline_extracts_bolded_names_with_month_dates():
    leads = parse_timeline(SAMPLE)
    by_name = {l["name"]: l for l in leads}
    assert by_name["ChatGPT"]["date"] == "2022-11-01"
    assert by_name["ChatGPT"]["precision"] == "month"
    assert by_name["Midjourney v4"]["date"] == "2022-11-01"
    assert by_name["GPT-4"]["date"] == "2023-03-01"
    # two bolded names in one entry both become leads
    assert "GPT-4 API" in by_name
    # html tags stripped from context
    assert "<b>" not in by_name["ChatGPT"]["context"]


def test_parse_timeline_year_only_falls_back_to_year_precision():
    sample = ("- year: 2021\n  events:\n  - date:\n    info:\n"
              "    - text: <b>Model X</b> ships.\n")
    leads = parse_timeline(sample)
    assert leads[0]["date"] == "2021-01-01"
    assert leads[0]["precision"] == "year"
