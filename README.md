<p align="center">
  <img src="site/assets/logo.svg" alt="LLM ledger" width="420">
</p>

<p align="center">
  <strong>Explore the dataset online: <a href="https://ledger.yasamanansari.com">ledger.yasamanansari.com</a></strong><br>
  by <a href="https://yasamanansari.com">Yasaman Ansari</a>
</p>

Ask "when was OpenAI's o3 released?" and you get four honest answers:

| event | date |
|---|---|
| announced | 2024-12-20 |
| o3-mini shipped | 2025-01-31 |
| in the API (`api_ga`) | 2025-04-16 |
| o3-pro shipped | 2025-06-10 |

Most catalogs collapse that into one "release date", and papers on the
same model end up using different days. This dataset keeps each moment
as its own row, with a date, how precise it is, the page it came from,
and how sure we are. Epoch AI tracks how big a model is; we track
**when** things happened. The two join on a shared key.

**Newest releases first:**
[`data/generated/models_latest.csv`](data/generated/models_latest.csv)
is a reading view of `models.csv`: the identifying columns, first public
availability date first, most recent releases at the top. It is rebuilt
on every update.

## How the data is shaped

![Entity-relationship diagram of the six core tables](docs/erd.svg)

Read it left to right. **Organizations** build **models**. A model does
not have a date; it has a life, and each moment of that life is a row in
**events**: announced, previewed, opened in the API, weights published,
retired. Every machine-dated event keeps its receipts in **claims**, one
row per source that had an opinion, so the verdict can be re-judged from
the evidence. **Crosswalk** maps a model's names across catalogs (the
same model is `gpt-4o` to OpenAI and `openai/gpt-4o` on OpenRouter), and
**attributes** is the spec sheet: context, modalities, prices.

`events.csv` is the real data. Everything under `data/generated/` is that
table re-arranged for convenience. Dates on `models.csv` such as
`first_public_availability_date` are computed from events; do not edit
them by hand.

Beside the core sits **observations** (`data/observations/`): what a
source said and when, kept as stated rather than judged. Which
providers listed a model at what price and limits, and which Hub commit
or API snapshot was served, are runs of days; which arXiv papers named a
model is one row per paper version. Generated views join them back to
models on `model_id`.

| I want | Open this |
|---|---|
| newest releases at the top | [`data/generated/models_latest.csv`](data/generated/models_latest.csv) |
| one row per model, dates as columns | [`data/generated/llm_ledger_wide.csv`](data/generated/llm_ledger_wide.csv) |
| that plus Epoch scale columns | [`data/generated/llm_ledger_enriched.csv`](data/generated/llm_ledger_enriched.csv) |
| capability scores (Epoch ECI) by model | [`data/generated/llm_ledger_capability.csv`](data/generated/llm_ledger_capability.csv) |
| benchmark scores (Epoch Benchmarking Hub) by model | [`data/generated/llm_ledger_benchmarks.csv`](data/generated/llm_ledger_benchmarks.csv) |
| LMArena ratings by model and leaderboard date | [`data/generated/llm_ledger_arena.csv`](data/generated/llm_ledger_arena.csv) |
| every dated fact with a source | [`data/core/events.csv`](data/core/events.csv) |
| every source behind a machine-dated fact | [`data/core/claims.csv`](data/core/claims.csv) |
| who made the model | [`data/core/models.csv`](data/core/models.csv), [`organizations.csv`](data/core/organizations.csv) |
| other names for the same model | [`data/core/crosswalk.csv`](data/core/crosswalk.csv) |
| how many Hub fine-tunes, quantizations, merges and adapters name a model's repo as their base | [`data/generated/hub_descendants.csv`](data/generated/hub_descendants.csv) |
| context / prices / modalities | [`data/core/attributes.csv`](data/core/attributes.csv) |
| which provider listed a model, at what price and limits, on each day | [`data/observations/`](data/observations/) (availability, price, capability) |
| prices since 2023, from LiteLLM's git history | [`data/observations/price_observations.csv`](data/observations/price_observations.csv) (source `litellm_git`), changes in [`price_changes.csv`](data/generated/price_changes.csv) |
| weekly Hugging Face downloads since 2024-07 and ModelScope downloads | [`data/observations/download_observations.csv`](data/observations/download_observations.csv) |
| OpenRouter's daily top-50 models by tokens since 2025 | [`data/observations/usage_observations.csv`](data/observations/usage_observations.csv) |
| when a model stopped being top-ranked (LMArena top 30) and stopped being used (OpenRouter top 50) | [`data/generated/obsolescence.csv`](data/generated/obsolescence.csv) |
| which exact version was served: Hub commit, API snapshot id | [`data/observations/model_versions.csv`](data/observations/model_versions.csv) |
| everything on offer on one day, by provider, with prices | [`data/generated/market_on_date.csv`](data/generated/market_on_date.csv) (newest day; `pipeline/market.py --date D` for any other) |
| which arXiv papers name a model, and how soon after release | [`data/observations/research_mentions.csv`](data/observations/research_mentions.csv), [`research_mentions_monthly.csv`](data/generated/research_mentions_monthly.csv), [`research_first_mentions.csv`](data/generated/research_first_mentions.csv) |
| how often a model's paper is cited, by year | [`data/observations/citation_observations.csv`](data/observations/citation_observations.csv) (OpenAlex and Semantic Scholar, counts as each states them) |
| one topic as a ready set of files with its methods page | `make bundles` writes `dist/bundles/llm-ledger-{markets,science,lineage,governance}.zip`; methods in [`docs/bundles/`](docs/bundles/) |
| lab icons | [`assets/orgs/`](assets/orgs/) (`{org_id}.svg`) |
| how well each lab is covered | [`data/generated/coverage_report.md`](data/generated/coverage_report.md) |
| where catalogs disagree | [`data/generated/disagreement_report.md`](data/generated/disagreement_report.md) |
| how much "the date" moves | [`data/generated/sensitivity_report.md`](data/generated/sensitivity_report.md) |
| when a source moved a date it had stated (vendor reschedules) | [`data/generated/reschedules.csv`](data/generated/reschedules.csv) |
| what still needs a person, and how to settle it | [`data/staging/review_queue.csv`](data/staging/review_queue.csv), [`review_decisions.csv`](data/staging/review_decisions.csv) |

Columns and allowed values: [`docs/schema.md`](docs/schema.md).

## How a date gets decided

A date enters the ledger one of two ways.

A curator opens the primary page, a vendor blog post or a deprecation
table, reads the date, and writes the row. `verified_by` records who:
a person's name, or `llm-ledger` / `llm-ledger-agent` when the
project's LLM-assisted curation did the reading. Scripts never touch
those rows. Today no row carries a person's name; the `curated` status
below says exactly that.

Or a script pulls it from a catalog: Hugging Face, models.dev,
OpenRouter, the vendors' own model lists, Azure and Bedrock lifecycle
tables, the Wayback Machine. Every catalog date becomes a claim, and one
policy (`pipeline/confidence.py`) turns claims into a verdict:

- one source alone is `inferred`;
- two independent sources that agree within two days are `verified`,
  signed `llm-ledger`;
- a platform's own record of its own event (an OpenRouter listing, an
  Azure retirement schedule) is `verified` on its own and outranks any
  third-party copy of it; a copy that differs is noted, not disputed;
- stated dates from independent sources that clash by more than 30 days
  are `disputed`, with every value kept in `notes`.

Repo and registry creation timestamps can corroborate a date but never
set one on their own, because a Hugging Face repo is usually created
before the public launch (16 of 20 checkable cases; up to three weeks).
The full reasoning is in [`docs/methodology.md`](docs/methodology.md);
where the dates come from is in [`docs/sources.md`](docs/sources.md).

Operating rules that fall out of this:

- One event, one date, one URL. If the source only says "March 2024",
  we store `2024-03-01` and `precision=month`. We do not guess the day.
- Hugging Face `createdAt` of 2022-03-02 is a backfill, never a weights
  date. The Hub sweep keeps the top 40 repos per lab by downloads
  (`PER_ORG_CAP` in `pipeline/hf_census.py`); repos already in the ledger
  stay tracked when they fall out of the top 40. A repo counts when the
  Hub tags it `text-generation` or `image-text-to-text`, or when it has no
  tag but declares vLLM serving (Mistral's own-format weights carry no
  tag). Intermediate training checkpoints are not releases.
- Names: exact match first. Fuzzy score >= 97 joins; 92-97 waits for a
  person; below 92 is no match.
- We looked for Chinese labs on purpose: their Hugging Face namespaces
  are swept, and ModelScope's public search is swept for the same labs
  so a twin repo can corroborate a Hub date. Vendor APIs skip if there
  is no key.
- A name on Wikipedia or a community timeline is a lead, not a fact. It
  sits in `data/staging/review_queue.csv` until a vendor page, Hub
  timestamp, or arXiv v1 backs it.
- A repo re-hosted under another lab's namespace is a lead, not a
  release. Packaging suffixes (FP8, BF16, INT4, an `-hf` or `-vllm`
  conversion, a Petals build)
  never create a second model. API aliases (`-latest`, `deepseek-chat`)
  are not models. Image, video and music generators, embeddings and
  rerankers are out of scope by name.
- A models.dev date needs the vendor's own provider entry or a majority
  of resellers. When resellers disagree with no majority, no date is
  claimed and the case goes to the review queue.
- Dates read from timestamps (Hub `createdAt`, OpenRouter `created`,
  vendor registries) are UTC calendar dates; dates read from a page are
  as the page prints them. Expect one-day offsets for launches late in
  the US day or early in the Beijing day; the confidence policy allows
  two days for exactly this reason.

## Using it

```python
import pandas as pd

events = pd.read_csv("data/core/events.csv", parse_dates=["date"])
wide = pd.read_csv("data/generated/llm_ledger_wide.csv")

gap = (pd.to_datetime(wide["api_ga_date"]) -
       pd.to_datetime(wide["announced_date"])).dt.days.dropna()
print(gap.describe())
```

For research:

- **Filter first.** `events.confidence == "verified"` is the defensible
  sample; `models.first_availability_confidence` says how the headline
  date was reached, and `events.verified_by` says who signed it (so far
  only the project and its agent, never a named person). The rest is a
  good lead list, not a fact list.
- **Pick the event that answers your question.** Adoption shocks:
  `api_ga` for developers, `weights_released` for the open ecosystem,
  `consumer_rollout` / `free_tier` for the public. `announced` is when
  people first heard. `platform_availability` (with `platform`) is when
  a cloud started serving it; `retired` with a `platform` is that host's
  shutdown, not the vendor's.
- **Open weights are not open source.** `access_type = open_weights`
  only says the weights can be downloaded. A model is fully open when its
  `license_family` is `osi_approved` or `permissive` and both
  `training_data_released` and `training_code_released` are `true`
  (OLMo, Pythia, SmolLM). Blank means not reviewed, not "no".
- **Know the biases.** Hub-only weights dates are `inferred` on purpose.
  Coverage is deepest for OpenAI and open-weight labs, thinnest for
  closed labs without an API listing. Every machine date's evidence is
  in `claims.csv`; every `disputed` row lists all values in `notes`.
- **Keep `source_url`.** It is the page a reader can open.

## How much is in it

<!-- stats:start -->
Data as of 2026-10-29, the latest source pull. Exact counts: 1845 models from 75 organizations, 2871 dated events, backed by 4555 live source claims. First availability runs from 2021-11-18 to 2026-10-27. 87% of the models are open-weight; Chinese labs make up 34% of those.

Read the counts together with their confidence labels. 41% of events are `verified` (two independent sources agreed within two days, or a platform reported its own listing); 29% of those are a platform's own listing timestamp, and 0 were checked by a named person. Per model: 4% have a verified event a person read from a primary page such as a vendor blog or deprecation table, 36% have only machine-corroborated events, and the remaining 60% rest on a single source. Filter on `events.confidence` before treating a date as settled.
<!-- stats:end -->

Per-lab detail is in [`coverage_report.md`](data/generated/coverage_report.md),
rebuilt with the data. The paragraph above is written by `pipeline/build.py`
on every rebuild and checked by validation, so it cannot drift from the
tables.

## What is in and what is out

**In:** a named checkpoint from a lab (Qwen2.5-72B Instruct, Claude 3
Opus, Llama 3 70B).

**Out, unless the thing is famous on its own:**

- GGUF / GPTQ / AWQ: same model, packed for a laptop
- LoRA / adapters: a small patch on someone else's weights
- community merges: hobby blends, not a lab release

Count every GGUF and we would have fifty Qwen2.5-72Bs. We want one.

Also out of the core tables: scores, parameter counts, training cost
(use [Epoch](https://epoch.ai/data/ai-models)), laws, usage stats.
Epoch's capability and benchmark scores and LMArena's ratings are joined
in generated files (`llm_ledger_capability.csv`,
`llm_ledger_benchmarks.csv`, `llm_ledger_arena.csv`), never copied into
core.

This is a first cut, not everything. More models can go in. GGUFs
still will not.

## Rebuild

The pipeline that produces every file under `data/` lives here so the
dataset can be rebuilt and audited: anyone who doubts a date can
re-derive it. It runs on Python 3.11, the version the daily job uses;
`requirements.txt` is pinned to the exact versions that job runs, so it
reads as a lockfile, and newer minor versions will most likely work. The
LLM-assisted discovery agent that drafts new rows for review runs from a
separate repository: it holds API credentials and unreviewed drafts,
neither of which belongs in a dataset.

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
make all   # pull match reconcile census lifecycle observe build validate test
```

Generated files rebuild the same way every time. We do not commit raw
third-party dumps, only their URL and hash, so a fresh clone must run
`make pull` before the loaders; loaders refuse a snapshot older than
three days unless `LEDGER_ALLOW_STALE=1` is set. A failed puller fails
the run: nothing is committed on a day a source could not be read.

## More

- [`docs/schema.md`](docs/schema.md): tables and allowed values
- [`docs/sources.md`](docs/sources.md): where dates come from
- [`docs/methodology.md`](docs/methodology.md): inclusion and checks
- [`docs/bundles/`](docs/bundles/): methods for the Markets, Science,
  Lineage and Governance bundles (`make bundles`)

## License

The dataset (everything under `data/`) is licensed under the
[Creative Commons Attribution 4.0 International License](LICENSE)
(CC BY 4.0). You may copy, redistribute, and build on it for any
purpose, including commercially, provided you credit "Yasaman Ansari,
llm-ledger", link to the license, and indicate any changes you made.

The source code (`pipeline/`, `tests/`, `Makefile`) is licensed under the
[MIT License](pipeline/LICENSE).

Upstream data incorporated here: [Epoch AI, "Data on AI Models"](https://epoch.ai/data/ai-models)
(CC BY 4.0), used in `data/generated/llm_ledger_enriched.csv` and as one
dating signal among several; [Epoch AI, "Epoch Capabilities Index"](https://epoch.ai/eci)
(CC BY 4.0), used in `data/generated/llm_ledger_capability.csv`; [Epoch AI, "AI Benchmarking Hub"](https://epoch.ai/benchmarks)
(CC BY 4.0), used in `data/generated/llm_ledger_benchmarks.csv`; [LMArena, "leaderboard-dataset"](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset)
(CC BY 4.0), used in `data/generated/llm_ledger_arena.csv`; [NHLOCAL, "AiTimeline"](https://github.com/nhlocal/AiTimeline)
(MIT), used as a discovery lead for pre-API-era models; [arXiv](https://arxiv.org)
paper metadata (CC0 1.0, via OAI-PMH), used in `research_mentions.csv`;
[BerriAI, "litellm"](https://github.com/BerriAI/litellm) price table history (MIT), used in
`price_observations.csv`; [cfahlgren1, "hub-stats"](https://huggingface.co/datasets/cfahlgren1/hub-stats)
(Apache-2.0), used in `download_observations.csv` and `hub_descendants.csv`; [OpenAlex](https://openalex.org)
(CC0) and [Semantic Scholar](https://www.semanticscholar.org) citation counts, used in
`citation_observations.csv`; and OpenRouter's daily rankings,
used in `usage_observations.csv`: "Source: OpenRouter (openrouter.ai/rankings), as of
the `as_of` date in each row. Licensed under CC BY 4.0." The terms every
other source is used under are listed in [`docs/sources.md`](docs/sources.md);
from them we keep individual facts and their URLs, not copies of content.

## How to cite

If this dataset contributes to published work, please cite it. GitHub's
"Cite this repository" button reads [`CITATION.cff`](CITATION.cff);
the BibTeX equivalent is:

```bibtex
@misc{llmledger2026,
  author = {Ansari, Yasaman},
  title  = {llm-ledger: a provenance-tracked dataset of dated events in the
            lifecycle of large language models},
  year   = {2026},
  url    = {https://github.com/YasamanAnsari/llm-ledger}
}
```

