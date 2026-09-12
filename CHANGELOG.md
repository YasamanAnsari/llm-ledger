# Changelog

All notable changes to the llm-ledger dataset and pipeline are recorded here.
Data corrections update rows in place; this file preserves the history.

## 2026-09-11 (v2026.10)

Identity, scope and provenance overhaul after a full audit of the data and
workflows. Column layout of `models.csv` gains one derived column; model
ids for packaging variants changed; v2026.09 remains available as a tag.

Policy (every rule below is enforced by a validation rule or a test):

- `models.review_status` is removed. Its levels were a roll-up of
  `events.confidence`, `source_type` and `verified_by`, and its top
  level (`human_reviewed`) never applied: no event has been signed by a
  named person. The one thing it did internally, telling loaders which
  models are curated so their `family`, `variant_role` and `access_type`
  are left alone, is now `confidence.curated_model_ids`, computed from
  the events on every run. The coverage report counts models as
  curated / corroborated / single-source instead.
- One agreement window. Two stated machine dates corroborate within two
  days, the same window bracketing timestamps already had (`AGREE_DAYS`;
  the 7-day stated-claim window and `BOUND_AGREE_DAYS` are gone). No row
  changed: every verified machine event already sat within two days.
- A first-party record is never `disputed` by a third party. When Azure
  moved four o-series retirements to 2026-11-19, LiteLLM still carried
  the old dates and the rows were marked disputed against a stale
  mirror. The platform's own schedule now stands as `verified`; a
  differing mirror is written to `notes` as `differs:`, an agreeing one
  as `agrees:` (not as independent corroboration). 4 rows change
  (3 disputed -> verified, 1 inferred -> verified); 67 notes reworded.
- `claims.csv` keeps what a source said before it moved its date. New
  column `superseded_on` (empty on the live row; the pull date that saw
  the change on the old one); primary key is now
  `(event_id, source_url, date)`. Loaders re-assess from live rows only.
  New validation rule 14: a superseded claim has a live claim from the
  same source on the same event. New artifact
  `data/generated/reschedules.csv`: one row per move, signed in days.
  Backfilled 6 moves from the daily snapshots since v2026.09, taking only
  pairs of consecutive daily updates with no code change in between
  (Epoch 2026-09-03: 1, OpenRouter 2026-09-05: 1) plus Azure's four
  o-series moves of 2026-09-12, confirmed against the raw page snapshots.
- `first_public_availability_date` ignores `quarter`/`year` placeholders
  (8 models lose a Jan-1 headline date); new derived column
  `first_availability_confidence`.
- `platform` is a controlled vocabulary (`aws_bedrock`->`bedrock`,
  `gcp_vertex`->`vertex`, `azure_openai`->`azure`: 8 rows).
- Machine rows must carry claims and curated rows none (rule 11); one
  model per machine identifier, snapshots excepted (rule 12); `api_only`
  is incompatible with a `weights_released` event (rule 13).
- An Archive capture never dates a release on its own and never outranks
  repo creation; a capture that predates the repo is a recreated repo and
  is discarded (`hf_recreated_repo` review rows).
- OpenRouter expirations are `retired` on `platform=openrouter`, first
  party (3 rows were vendor-scoped).
- Packaging suffixes (FP8, BF16, INT4/INT8, `-hf`, `-paddle`, tensor
  shards) are stripped from identity: 60 duplicate rows merged into their
  base, 49 renamed.
- A base checkpoint and its instruct/chat checkpoint are distinct models:
  22 repos detached and re-drafted as their own rows; a role-suffixed
  repo may still attach to a catalog-only row, which names the served
  checkpoint.
- Another lab's weights re-hosted under a different namespace are leads
  (`hf_mirror_repo`), never releases: 13 rows drafted from Nous Research
  and other mirrors deleted and re-drafted from the official repos
  (Llama 2, Llama 3, Llama 3.1, Llama 3.2 now attributed to Meta). A
  foreign family token under the publisher's own name is a `finetune`
  derivative (43 rows flagged).
- Aliases (`-latest`, `deepseek-chat`), image/video/music generators,
  embeddings, rerankers, speech utilities and reward models are out of
  scope by name or by modality: 37 rows deleted.
- models.dev dates require the vendor's own provider entry or a strict
  majority of resellers; disagreement yields no claim and a
  `md_no_consensus` review row (51 queued). A row of the other
  availability type resting on models.dev alone is withdrawn; a catalog
  row left without any anchor event is withdrawn.
- `license_family` no longer guesses from `other`/`unknown` (162 rows
  cleared); OpenRAIL is not OSI-approved; api-only drafts are
  `proprietary` (202 rows filled).
- `record_updated` is stamped by the loaders on every model they change.
- 18 Epoch-sourced `announced` rows without claims had their single claim
  backfilled; 18 wayback-sourced weights rows were reset to their repo
  claim.
- README headline statistics are generated by `build.py` and checked by
  validation rule 9.
- ModelScope is swept through its public search (no token) for the
  Chinese labs' namespaces; the lab's twin repo there is a bound like the
  Hub's, and two creations within two days corroborate: 91 weights rows
  move `inferred` -> `verified`, 2 gain a date they lacked. A bound that
  trails the chosen date by more than two days is lag and no longer
  blocks corroboration; one that leads it keeps the row `inferred` (3
  rows).
- Mistral's `/models` is normalized: `created` is the response time and
  is never a claim; `deprecation` is a first-party retirement; ids the
  vendor lists as aliases of one another across several ledger rows are
  queued as `vendor_alias_group` (5 groups).
- `data/staging/review_decisions.csv` closes the review loop: an
  accepted `fuzzy_match` joins with method `reviewed`; rejected or
  dismissed rows are never queued again. Hub namespaces with in-scope
  repos and no org mapping are queued once each (`hf_unmapped_namespace`).
- Snapshot dates carried into artifacts (`epoch_snapshot_date`,
  `price_date`) follow payload content, not pull day; the coverage and
  sensitivity reports are written by `build` and covered by rule 9. The
  daily run no longer rewrites unchanged rows.
- A failed puller fails the run; loaders refuse snapshots older than
  three days and skip days whose pull left no payload.

Table sizes: models 1215 -> 1135, events 2029 -> 1874, claims 2777 -> 2884,
crosswalk 2225 -> 2133, attributes 424 -> 390. The v2026.09 tables were
repaired by a one-time script (since deleted); every rule it applied is
enforced by the loaders and validation from this release on.

## 2026-09-10

- `models.family` and `models.variant_role` are now read off the model
  name for every model a person has not reviewed
  (`schema.family_and_role`; 45 of 55 curated families reproduced, the
  rest are version-collapsing conventions). `family` coverage 5% -> 100%.
  `variant_role` loses the `other` placeholder and becomes optional: empty
  means the name does not say (54% of rows); the rest carry one of nine
  classes. Curated values on `human_reviewed` models stand.
- Dropped `models.co_developer_org_ids` (never used) and
  `models.developing_lab` (23 rows, all repeating the developer's name).
- `models_latest.csv` is now an 11-column reading view (dates, identity,
  developer, family, role, type, access, license family, review status);
  the sparse curated columns stay in `models.csv`.
- Bedrock lifecycle puller follows AWS's 2026-09-07 page split: the dated
  EOL table now lives on `model-lifecycle-legacy.html`. Models launched
  after that date publish EOL only on model cards and via the
  authenticated `ListFoundationModels` API, which we do not call yet.
- models.dev release dates: when resellers disagree with no majority, the
  later date is kept (`match.consensus_date`). A lone reseller's earlier
  outlier had moved `gemini-3-pro` availability before its announcement
  and blocked the daily update.
- reconcile withdraws a stale machine `announced` row whenever a catalog
  moves availability in front of it, not only on runs that re-draft the
  announcement.

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
