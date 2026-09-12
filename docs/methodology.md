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
3. Other open-weight models (Hugging Face; ModelScope for the Chinese
   labs)
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
   timestamp alone is `inferred`; it becomes `verified` only when an
   independent bound lands within two days of it: the first public
   Wayback capture of the repo, or the lab's twin repo on ModelScope
   (swept through its public search; its creation time is a bound like
   the Hub's). A bound that trails the Hub date by more than two days is
   lag (a late crawl, a mirror made months later) and is only noted; one
   that leads it keeps the row `inferred`, because the weights may have
   been public there first. The Hub row keeps the date either way.
   A capture alone never dates anything, and a capture that predates the
   repo's creation means the repo was deleted and recreated or renamed:
   the capture is discarded and the case queued (`hf_recreated_repo`).
   Only the publisher's own repo dates a release; a copy re-hosted under
   another namespace is a lead (`hf_mirror_repo`).
6. The same holds for vendor model registries: OpenAI's and Anthropic's
   `created` timestamps run 1-16 days ahead of the public launch. They
   corroborate a catalog date; they do not set it. Mistral's `created` is
   the response time and is ignored entirely.
7. Catalogs: a models.dev date is used when the vendor's own provider
   entry states it, or a strict majority of resellers agree. A lone
   reseller yields an `inferred` claim; resellers that disagree with no
   majority yield no date and a `md_no_consensus` review row. A Jan-1
   date is a year placeholder and never becomes the headline date.
8. Time zones: dates derived from timestamps are UTC calendar dates;
   dates read from a page are as printed. A launch late in the US day or
   early in the Beijing day can land a day apart across sources; the
   two-day bound window absorbs this.

If the source only gives a month, we store the first of that month and
`precision=month`. We do not invent a day. A catalog that says
"January 1" for a model with no known day is stored at `precision=year`.

## How sure we are

One policy in `pipeline/confidence.py` decides every machine-dated row;
every claim it weighed is kept in `data/core/claims.csv`. A source that
changes its date does not overwrite its earlier claim: the old row is
kept with `superseded_on` = the pull date that saw the change, only the
live row counts as evidence, and `data/generated/reschedules.csv` lists
every such move with its signed size in days. Vendors reschedule
shutdowns; that is a fact about the vendor, and it is recorded rather
than lost.

- `verified`: a curator read a primary source (`verified_by` is a
  person's name, or `llm-ledger` / `llm-ledger-agent` when the project's
  LLM-assisted curation did the reading), or `verified_by=llm-ledger`
  on a machine row: two independent machine sources agree within two
  days, or a platform reported its own event (OpenRouter's listing date, Azure's retirement schedule).
- `inferred`: one machine source, or sources that differ by 3-30 days.
- `disputed`: two stated dates disagree by more than 30 days. The
  best-evidenced date stays in `date`; everything else is in `notes`.
  A first-party record (the platform's own retirement table, a
  registry's own listing date) is never disputed by a third party: a
  mirror that differs is a stale or wrong transcription and is only
  noted (`differs:` in `notes`). Two first-party records can still
  dispute each other.
- A machine date that falls *before* a human-verified announcement is
  pre-staging (a repo or model object created ahead of launch) and is
  not loaded at all.

There is no per-model review grade: the event rows carry everything
(`confidence`, `source_type`, `verified_by`), and no event has been signed
by a named person yet. Most models rest on a single source. See
`data/generated/coverage_report.md` for the honest per-lab picture and
`disagreement_report.md` for where catalogs differ.

## How we update

Every day: `make all`. The pullers refresh every snapshot; the loaders
(`reconcile`, `hf_census`, `lifecycle`) re-assess machine-owned rows from
the current claims and never touch a curated row; `build` recomputes
derived columns; `validate` must be green before anything is committed.

Weekly: read `data/staging/review_queue.csv` and
`data/generated/coverage_report.md`; verify the labs with the lowest
verified share first. Settle a queue row by appending a line to
`data/staging/review_decisions.csv` with the row's `kind`, `left_key`,
`right_key`, a decision (`accept`, `reject` or `dismiss`), your name and
the date. The next run applies it (an accepted `fuzzy_match` joins with
method `reviewed`) and never queues that item again.

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
- ModelScope is swept for the Chinese labs' namespaces only; a Hub
  model whose lab has no ModelScope presence gets no twin and stays
  `inferred` until a capture or a curated source dates it.
- `region=global` unless a source says otherwise.
