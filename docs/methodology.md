# Methodology

## Who gets in

A model is in if it is a **named trained checkpoint from a lab**.
Quant packs (GGUF, GPTQ, AWQ), LoRA adapters, and community merges stay
out unless the thing is famous on its own.

If we keep a derivative, we mark `is_derivative=true` and point at
`base_model_id`.

We care most about LLMs, VLMs, and multimodal models, in this order:

1. Frontier / API labs (OpenAI, Anthropic, Google, Meta, Mistral, xAI,
   Cohere, Amazon)
2. Chinese labs we sweep on purpose: Qwen, DeepSeek, Moonshot, Zhipu,
   Baidu, Tencent, MiniMax, ByteDance, Meituan, Xiaomi, 01.AI, Baichuan,
   iFlytek, StepFun, Shanghai AI Lab, OpenBMB, IEIT, Skywork, RWKV,
   Ant Group
3. Other open-weight models (Hugging Face; ModelScope if we have a
   login)
4. Older models (GPT-1/2/3, BERT era), usually as leads first

## How we date a row

1. Use the primary source in [sources.md](sources.md).
2. If the page looks undated or edited later, check Wayback.
3. Save the URL we actually opened.
4. Papers: arXiv **v1** date, not a later revision.
5. Weights: the vendor's announcement wins. Hugging Face `createdAt` is
   when the repo was *created*, and labs create repos private and flip
   them public at launch. Across the models where we have both, the repo
   predates the launch in 16 of 20 cases, by up to three weeks. So a Hub
   timestamp alone is `inferred`; it becomes `verified` only when the
   first public Wayback capture of the repo lands within two days of it.
6. The same holds for vendor model registries: OpenAI's and Anthropic's
   `created` timestamps run 1-16 days ahead of the public launch. They
   corroborate a catalog date; they do not set it.

If the source only gives a month, we store the first of that month and
`precision=month`. We do not invent a day. A catalog that says
"January 1" for a model with no known day is stored at `precision=year`.

## How sure we are

One policy in `pipeline/confidence.py` decides every machine-dated row;
every claim it weighed is kept in `data/core/claims.csv`.

- `verified`: a person opened a primary source (`verified_by` is their
  name), or `verified_by=llm-ledger`: two independent machine sources
  agree within 7 days (2 days when one is a bracketing timestamp), or a
  platform reported its own event (OpenRouter's listing date, Azure's
  retirement schedule).
- `inferred`: one machine source, or sources that differ by 8-30 days.
- `disputed`: two stated dates disagree by more than 30 days. The
  best-evidenced date stays in `date`; everything else is in `notes`.
- A machine date that falls *before* a human-verified announcement is
  pre-staging (a repo or model object created ahead of launch) and is
  not loaded at all.

Per model, `review_status` summarizes this: `human_reviewed`,
`machine_corroborated`, or `unreviewed`. Most rows are `unreviewed`
catalog drafts. See `data/generated/coverage_report.md` for the honest
per-lab picture and `disagreement_report.md` for where catalogs differ.

## How we update

Every day: `make all`. The pullers refresh every snapshot; the loaders
(`reconcile`, `hf_census`, `lifecycle`) re-assess machine-owned rows from
the current claims and never touch a curated row; `build` recomputes
derived columns; `validate` must be green before anything is committed.

Weekly: read `data/staging/review_queue.csv` and
`data/generated/coverage_report.md`; verify the labs with the lowest
verified share first.

Monthly: rebuild, append `CHANGELOG.md`, tag `vYYYY.MM`.

Fixes edit the row. `record_created` / `record_updated` and the
changelog keep history.

## Name matching

`pipeline/match.py` cleans names, then exact-matches, then fuzzy
matches. Score >= 97 joins. 92-97 waits for a person. Below 92 is no
match. We keep that bar high on purpose.

## Limits

- Hugging Face `createdAt` before March 2022 is a fake backfill. Do
  not treat 2022-03-02 as a weights date.
- Hugging Face `createdAt` in general is a lower bound, not a release
  date (see above). Coverage skews toward open-weight models because the
  Hub is sweepable and vendor blogs are not.
- Wayback first captures lag by months for small repos, so many Hub
  dates stay `inferred` even when they are right.
- No ModelScope token: we use Hugging Face instead of inventing rows.
- `region=global` unless a source says otherwise.
