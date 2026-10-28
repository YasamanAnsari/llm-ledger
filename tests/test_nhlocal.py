"""Discovery sweeps: the NHLOCAL timeline parser and announce leads, and
arXiv paper leads."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from pull_arxiv import families_without_paper, names_family, paper_leads
from pull_nhlocal import announce_leads, parse_timeline

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


def test_announce_leads_name_only_models_missing_announced_at_the_earliest_mention():
    leads = parse_timeline(SAMPLE + "  - date: May\n    info:\n    - text: <b>GPT-4</b> again.\n")
    models = [{"model_id": "gpt-4"}, {"model_id": "chatgpt"}]
    events = [{"model_id": "chatgpt", "event_type": "announced"}]
    (row,) = announce_leads(leads, models, events)
    assert (row["kind"], row["left_key"], row["right_key"]) == ("announce_lead", "gpt-4", "2023-03")


def test_paper_leads_keep_titles_about_the_family_inside_the_release_window():
    assert names_family("Gemma 3 Technical Report", "Gemma 3")
    assert names_family("Kimi K2: Open Agentic Intelligence", "Kimi K2")
    assert names_family("GLM-4.5", "GLM 4.5")
    assert not names_family("Tuning Qwen2.5-VL to Improve Its Web Skills", "Qwen2.5-VL")
    assert not names_family("Phi-4-reasoning Technical Report", "Phi-4")

    def model(model_id, family, day):
        return {"model_id": model_id, "family": family, "developer_org_id": "google",
                "first_public_availability_date": day}
    models = [model("gemma-3-27b-it", "Gemma 3", "2025-03-12"),
              model("gemma-2-27b-it", "Gemma 2", "2024-06-27"),
              model("gemma-4-31b-it", "Gemma 4", "")]
    events = [{"model_id": "gemma-2-27b-it", "event_type": "paper_published"}]
    families = families_without_paper(models, events)
    assert [f[1] for f in families] == ["Gemma 3"]
    found = {"Gemma 3": [("2503.19786v1", "Gemma 3 Technical Report", "2025-03-25"),
                         ("1901.00001v2", "Gemma 3 Technical Report", "2019-01-01"),
                         ("2504.18562v1", "A Gemma 3-Based Wildfire Model", "2025-04-20")]}
    (row,) = paper_leads(families, lambda family: found[family])
    assert (row["left_key"], row["right_key"]) == (
        "google/Gemma 3", "https://arxiv.org/abs/2503.19786")
