"""Pull published model-lifecycle schedules: Azure Foundry, Amazon Bedrock,
and the LiteLLM price registry's deprecation dates.

Each source is a structured table or JSON, parsed mechanically (no LLM),
and normalized to one shape under data/raw/<source>/<date>/normalized.csv:

    source, model_ref, platform, retire_date, detail, url

- azure_lifecycle:   Microsoft Learn retirement schedule. Tables with the
                     header Model/Version/Lifecycle/Retirement date/...; the
                     Version is the vendor snapshot date. platform=azure.
- bedrock_lifecycle: AWS Bedrock model lifecycle table; EOL date is the
                     retirement. platform=bedrock.
- litellm:           model_prices_and_context_window.json entries carrying
                     `deprecation_date`, sourced by LiteLLM from provider
                     lifecycle pages. platform = litellm_provider (empty when
                     the provider is the model's own vendor; lifecycle.py
                     resolves that).

A changed page or JSON shape raises: no fallback, no partial silent load.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch
import schema

AZURE_URL = "https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule"
BEDROCK_URL = "https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle.html"
LITELLM_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"

COLUMNS = ["source", "model_ref", "platform", "retire_date", "detail", "url"]

ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


class _Tables(HTMLParser):
    """Collect every <table> as a list of rows of cell text."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _tables(html: bytes) -> list:
    parser = _Tables()
    parser.feed(html.decode("utf-8", errors="replace"))
    return parser.tables


def parse_azure(html: bytes) -> list:
    rows = []
    for table in _tables(html):
        if not table or table[0][:4] != ["Model", "Version", "Lifecycle", "Retirement date"]:
            continue
        for cells in table[1:]:
            if len(cells) < 4:
                continue
            model, version, lifecycle, retirement = cells[:4]
            m = ISO_DATE_RE.search(retirement)
            if not m:
                continue  # "—": no retirement scheduled
            rows.append({
                "source": "azure_lifecycle",
                "model_ref": f"{model}-{version}" if ISO_DATE_RE.fullmatch(version) else model,
                "platform": "azure", "retire_date": m.group(1),
                "detail": f"lifecycle={lifecycle}; version={version}", "url": AZURE_URL,
            })
    if not rows:
        raise ValueError("Azure retirement page: no Model/Version/Lifecycle tables found; layout changed?")
    return rows


def parse_bedrock(html: bytes) -> list:
    rows = []
    for table in _tables(html):
        if not table or "Model ID" not in table[0] or "EOL date" not in table[0]:
            continue
        id_col, eol_col = table[0].index("Model ID"), table[0].index("EOL date")
        for cells in table[1:]:
            if len(cells) <= max(id_col, eol_col) or not cells[eol_col]:
                continue
            try:
                eol = datetime.strptime(cells[eol_col], "%B %d, %Y").date().isoformat()
            except ValueError:
                continue  # "N/A" or free text
            rows.append({
                "source": "bedrock_lifecycle", "model_ref": cells[id_col],
                "platform": "bedrock", "retire_date": eol,
                "detail": f"legacy={cells[table[0].index('Legacy date')]}"
                          if "Legacy date" in table[0] else "",
                "url": BEDROCK_URL,
            })
    if not rows:
        raise ValueError("Bedrock lifecycle page: no Model ID / EOL date table found; layout changed?")
    return rows


def parse_litellm(payload: bytes) -> list:
    data = json.loads(payload)
    if not isinstance(data, dict) or "sample_spec" not in data:
        raise ValueError("LiteLLM registry shape changed (no sample_spec)")
    rows = []
    for key, entry in data.items():
        if key == "sample_spec" or not isinstance(entry, dict):
            continue
        dep = entry.get("deprecation_date", "")
        if not dep or not ISO_DATE_RE.fullmatch(dep):
            continue
        rows.append({
            "source": "litellm", "model_ref": key,
            "platform": entry.get("litellm_provider", ""), "retire_date": dep,
            "detail": f"mode={entry.get('mode', '')}", "url": LITELLM_URL,
        })
    if not rows:
        raise ValueError("LiteLLM registry: zero deprecation_date entries; field renamed?")
    return rows


SOURCES = (
    ("azure_lifecycle", AZURE_URL, "retirement-schedule.html", parse_azure),
    ("bedrock_lifecycle", BEDROCK_URL, "model-lifecycle.html", parse_bedrock),
    ("litellm", LITELLM_URL, "model_prices_and_context_window.json", parse_litellm),
)


def main() -> int:
    for source, url, filename, parse in SOURCES:
        payload = fetch.get_bytes(url)
        schema.write_snapshot(source, filename, payload, url)
        rows = sorted(parse(payload), key=lambda r: (r["model_ref"], r["retire_date"]))
        out = schema.snapshot_dir(source) / "normalized.csv"
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        print(f"pull_lifecycle: {source}: {len(rows)} dated rows -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
