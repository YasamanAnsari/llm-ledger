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
| every source behind a machine-dated fact | [`data/core/claims.csv`](data/core/claims.csv) |
| who made the model | [`data/core/models.csv`](data/core/models.csv), [`organizations.csv`](data/core/organizations.csv) |
| other names for the same model | [`data/core/crosswalk.csv`](data/core/crosswalk.csv) |
| context / prices / modalities | [`data/core/attributes.csv`](data/core/attributes.csv) |
| lab icons | [`assets/orgs/`](assets/orgs/) (`{org_id}.svg`) |
| how well each lab is covered | [`data/generated/coverage_report.md`](data/generated/coverage_report.md) |
| where catalogs disagree | [`data/generated/disagreement_report.md`](data/generated/disagreement_report.md) |
| how much "the date" moves | [`data/generated/sensitivity_report.md`](data/generated/sensitivity_report.md) |

`events.csv` is the real data. The wide file is just that table flipped
wide. An empty cell means that event never happened. Dates like
`first_public_availability_date` on `models.csv` are computed; do not
edit them by hand.

This snapshot: **1,171 models**, **1,955 events**, **41 orgs**, backed by
1,997 recorded claims. First availability: 2021-11-18 (GPT-3 API) to
2026-09-01. About 78% open-weight; Chinese labs are about half of those.

Read the counts honestly: 55 models are `human_reviewed`, 291 are
`machine_corroborated` (two independent sources agreed), and 825 are
`unreviewed` catalog drafts. 632 of 1,955 events are `verified`.
[`coverage_report.md`](data/generated/coverage_report.md) has this per lab.

## How to use it

```python
import pandas as pd

events = pd.read_csv("data/core/events.csv", parse_dates=["date"])
wide = pd.read_csv("data/generated/llm_ledger_wide.csv")

gap = (pd.to_datetime(wide["api_ga_date"]) -
       pd.to_datetime(wide["announced_date"])).dt.days.dropna()
print(gap.describe())
```

### Using it for research

- **Filter first.** `models.review_status in {human_reviewed,
  machine_corroborated}` and `events.confidence == "verified"` is the
  defensible sample. The rest is a good lead list, not a fact list.
- **Pick the event that answers your question.** Adoption shocks:
  `api_ga` for developers, `weights_released` for the open ecosystem,
  `consumer_rollout` / `free_tier` for the public. `announced` is when
  people first heard. `platform_availability` (with `platform`) is when
  a cloud started serving it; `retired` with a `platform` is that host's
  shutdown, not the vendor's.
- **Know the biases.** Hugging Face repo creation runs ahead of the
  public launch (16 of 20 checkable cases; up to three weeks), so
  Hub-only weights dates are `inferred` on purpose. Coverage is deepest
  for OpenAI and open-weight labs, thinnest for closed labs without an
  API listing. Every machine date's evidence is in `claims.csv`; every
  `disputed` row lists all values in `notes`.
- **Keep `source_url`.** It is the page a reader can open.

Columns and allowed values: [`docs/schema.md`](docs/schema.md). How dates
and confidence are decided: [`docs/methodology.md`](docs/methodology.md).

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
- One confidence policy for every machine date
  (`pipeline/confidence.py`): one source is `inferred`; two independent
  sources agreeing are `verified` by `llm-ledger`; stated dates that
  clash are `disputed` with everything in `notes`. A human check carries
  that person's name. Repo and registry creation timestamps corroborate
  a date but never set one on their own.
- Hugging Face sweep keeps the **top 40 repos per lab** by downloads
  (`PER_ORG_CAP` in `pipeline/hf_census.py`); repos already in the
  ledger stay tracked when they fall out of the top 40.
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
make all   # pull match reconcile census lifecycle build validate test
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
