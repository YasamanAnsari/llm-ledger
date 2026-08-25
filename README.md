# llm-ledger

Dated events in the life of large language models. Each row has a date,
how precise it is, a source URL, and how sure we are.

Epoch AI tracks how big a model is. We track **when** things happened.
You can join the two.

## Why

"When was this model released?" has no single answer.

OpenAI's o3 in this file:

| event | date |
|---|---|
| announced | 2024-12-20 |
| in the API (`api_ga`) | 2025-04-16 |
| o3-mini shipped | 2025-01-31 |
| o3-pro shipped | 2025-06-10 |

Other catalogs usually smash that into one "release date." Papers on
ChatGPT already pick different days. We keep each moment as its own row
so you can choose the date that matches your question.

## Files

| I want | Open this |
|---|---|
| one row per model, dates as columns | [`data/generated/llm_ledger_wide.csv`](data/generated/llm_ledger_wide.csv) |
| that plus Epoch scale columns | [`data/generated/llm_ledger_enriched.csv`](data/generated/llm_ledger_enriched.csv) |
| every dated fact with a source | [`data/core/events.csv`](data/core/events.csv) |
| who made the model | [`data/core/models.csv`](data/core/models.csv), [`organizations.csv`](data/core/organizations.csv) |
| other names for the same model | [`data/core/crosswalk.csv`](data/core/crosswalk.csv) |
| context / current prices (flagships) | [`data/core/attributes.csv`](data/core/attributes.csv) |
| lab icons | [`assets/orgs/`](assets/orgs/) (`{org_id}.svg`) |
| where catalogs disagree | [`data/generated/disagreement_report.md`](data/generated/disagreement_report.md) |
| how much "the date" moves | [`data/generated/sensitivity_report.md`](data/generated/sensitivity_report.md) |

`events.csv` is the real data. The wide file is just that table flipped
wide. An empty cell means that event never happened. Dates like
`first_public_availability_date` on `models.csv` are computed; do not
edit them by hand.

This snapshot: **1,141 models**, **1,593 events**, **41 orgs**. First
availability: 2021-11-18 (GPT-3 API) to 2026-08-21. About 77%
open-weight; Chinese labs are about half of those.

## How to use it

```python
import pandas as pd

events = pd.read_csv("data/core/events.csv", parse_dates=["date"])
wide = pd.read_csv("data/generated/llm_ledger_wide.csv")

gap = (pd.to_datetime(wide["api_ga_date"]) -
       pd.to_datetime(wide["announced_date"])).dt.days.dropna()
print(gap.describe())
```

For a paper, prefer `confidence=verified` and keep `source_url`. If a
row is `disputed`, read `notes` before you pick a date.

Columns and allowed values: [`docs/schema.md`](docs/schema.md).

## What is in and what is out

**In:** a named checkpoint from a lab (Qwen2.5-72B Instruct, Claude 3
Opus, Llama 3 70B).

**Out, unless the thing is famous on its own:**

- GGUF / GPTQ / AWQ: same model, packed for a laptop
- LoRA / adapters: a small patch on someone else's weights
- community merges: hobby blends, not a lab release

Count every GGUF and we would have fifty Qwen2.5-72Bs. We want one.

Also out: scores, parameter counts, training cost (use
[Epoch](https://epoch.ai/data/ai-models)), laws, usage stats.

A name on Wikipedia or a community timeline is a **lead**. It sits in
`data/staging/review_queue.csv` until a vendor page, Hub timestamp, or
arXiv v1 backs it.

## Rules we actually follow

- One event, one date, one URL. If the source only says "March 2024",
  we store `2024-03-01` and `precision=month`. We do not guess the day.
- `verified`: a primary source backs the date. `verified_by=llm-ledger`
  means a project-level check; a human check carries that person's name.
  `inferred`: catalog only.
  `disputed`: sources disagree; all values stay in `notes`.
- Hugging Face sweep keeps the **top 40 repos per lab** by downloads
  (`PER_ORG_CAP` in `pipeline/hf_census.py`). Raise it to pull more.
- Hugging Face `createdAt` of 2022-03-02 is a backfill. We do not use
  it as a weights date.
- Names: exact match first. Fuzzy score >= 97 joins; 92-97 waits for
  a person; below 92 is no match.
- We looked for Chinese labs on purpose. ModelScope needs a login; we
  skip it rather than invent rows. Vendor APIs skip if there is no key.
- This is a first cut, not everything. More models can go in. GGUFs
  still will not.

## Rebuild

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
make pull match reconcile census build validate test
```

Generated files rebuild the same way every time. We do not commit raw
third-party dumps, only their URL and hash.

## More

- [`docs/schema.md`](docs/schema.md): tables and allowed values
- [`docs/sources.md`](docs/sources.md): where dates come from
- [`docs/methodology.md`](docs/methodology.md): inclusion and checks

## License

Code: [MIT](LICENSE-CODE). Data: [CC BY 4.0](LICENSE-DATA). You can
reuse the data; you must give credit (name, title, link, license).
That is the license. A paper citation is what we ask for on top.

Upstream: [Epoch AI](https://epoch.ai/data/ai-models) and
[NHLOCAL/AiTimeline](https://github.com/nhlocal/AiTimeline) (both CC BY
4.0). Other sites: we keep facts and URLs, not their dumps.

```bibtex
@misc{llmledger2026,
  author = {Ansari, Yasaman},
  title  = {llm-ledger: a provenance-tracked dataset of dated events in the
            lifecycle of large language models},
  year   = {2026},
  url    = {https://github.com/YasamanAnsari/llm-ledger}
}
```

[`CITATION.cff`](CITATION.cff) feeds GitHub's cite button.
