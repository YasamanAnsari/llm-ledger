# Changelog

All notable changes to the llm-ledger dataset and pipeline are recorded here.
Data corrections update rows in place; this file preserves the history.

## 2026-09-03

- New generated view `data/generated/models_latest.csv`: `models.csv`
  with `first_public_availability_date` as the first column, newest
  releases first, undated models last. Same values as `models.csv`;
  covered by validation rule 9.
- `docs/erd.svg`: entity-relationship diagram of the six core tables,
  embedded in the README and `docs/schema.md`.
- README reorganised to read front to back: the o3 example, the shape of
  the data, how a date is decided, then usage. Headline counts are now
  approximate with a pointer to `coverage_report.md` for exact numbers.

## 2026-09-01 (v2026.09)

Schema and confidence overhaul. Column layouts changed; event ids for
re-typed rows changed. v2026.08 remains available as a tagged release.

- New table `claims.csv`: every machine claim behind an event (source URL,
  date, precision, bound/first-party flags). Loaders re-assess events
  from the full claim set each run, so aggregator corrections propagate.
- One confidence policy (`pipeline/confidence.py`). Hugging Face
  `createdAt` alone is now `inferred` (it predates the public launch in
  16 of 20 checkable cases); it verifies only when the first Wayback
  capture agrees within two days. Vendor model-registry `created`
  timestamps are treated the same way. Machine dates earlier than a
  curated announcement are withdrawn as pre-staging.
- models.dev release dates on open-weights models are now
  `weights_released`, not `api_ga` (141 rows re-typed). OpenRouter
  listing dates are their own `platform_availability` rows
  (`platform=openrouter`) instead of masquerading as `api_ga`. Epoch
  publication dates later than an availability event are dropped (28
  rows). Catalog Jan-1 dates carry `precision=year`.
- New sources: OpenAI/Anthropic/Gemini `/models` (registry timestamps,
  OpenAI `shutdown_date`), Azure Foundry retirement schedule, Amazon
  Bedrock model lifecycle, LiteLLM deprecation dates, Internet Archive
  first captures. `retired` rows: 19 -> 170, platform-scoped where the
  schedule is a host's, not the vendor's.
- `attributes.csv` filled from models.dev for matched models (50 -> 415
  rows); new `reasoning_supported` column; `reasoning_type` optional;
  `pdf` added to modalities.
- `models.review_status` (derived): `human_reviewed` /
  `machine_corroborated` / `unreviewed`. New
  `data/generated/coverage_report.md`.
- Validation: availability more than 30 days before `announced` is an
  error; `platform` allowed on any event; claims table checked.
- Withdrawn: 1,373 machine-owned rows regenerated under the policy;
  7 undated catalog-drafted models removed; 6 unreviewed models gained
  `derivative_type=distill` from their names.
- Verified events 1,044 -> 632, of which 289 are platform-own listing
  timestamps and ~200 are curated. The old count was inflated by repo
  creation dates.

## 2026-08-25

- Initial repository scaffold: schema, validation rules, empty core tables.
- First ingestion: catalog pullers (models.dev, OpenRouter, Epoch AI, arXiv,
  keyed vendor APIs), cross-source matcher (493 models matched across >=2
  sources), reconciler loading 337 models / 433 inferred events, and the
  cross-source disagreement report.
- Primary-source verification for 56 core models (vendor blogs, deprecation
  pages, arXiv, HF Hub timestamps); 85.9% of in-scope availability events
  verified; cross-source date conflicts stored as disputed with all values
  in notes (Kimi K3 weights date, Mixtral aggregator claim). Attributes
  table populated for 50 models.
- Hugging Face open-weight sweep (2013 repos, inclusion rule applied,
  per-org download cap) adding ~730 models and ~830 `weights_released`
  events dated by repo `createdAt`; Chinese-lab share of open-weight rows
  50%. NHLOCAL AiTimeline (CC BY) discovery leads queued for review, never
  loaded into core.
- Vendor-changelog pass: 16 verified `price_changed` / `feature_added` /
  `alias_repointed` events for core models (Anthropic release notes, Mistral
  changelog, archived OpenAI announcements); one verified event dropped for
  a vocabulary gap and queued for review.
- Treatment-date sensitivity report from the ledger's own dates.
- Derived fields and wide/enriched artifacts rebuild byte-identically
  (validation rule 9); full-pipeline rerun confirmed idempotent.
- Deduplication audit: merged nine duplicate model rows caused by two
  identity-rule splits (vendor "qwen2-5" vs aggregator "qwen-2-5" spelling;
  short keys org-prefixed by reconcile but not the census). Matcher now
  bridges letter-digit boundary spellings, reconcile pins clusters to
  already-crosswalked identifiers, and both scripts share one slug rule.
  Filled availability gaps: GPT-4.5 consumer/API preview events from the
  archived launch post; three announced-only open-weight models dated from
  their HF repo timestamps.
