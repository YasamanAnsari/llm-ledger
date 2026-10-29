# Changelog

All notable changes to the llm-ledger dataset and pipeline are recorded here.
Data corrections update rows in place; this file preserves the history.

## 2026-10-28

- Price history back to 2023: `pipeline/pull_litellm_history.py` reads
  LiteLLM's `model_prices_and_context_window.json` at the last commit on
  `main` of every day from 2023-09-06 to 2026-10-02 (1,123 days, 602
  commits) and `observe.py` folds them as source `litellm_git`: 6,775
  price runs and 5,898 limit runs, 529 of them price changes in
  `price_changes.csv`. Dates are LiteLLM's commit days, an upper bound on
  the provider's change.
- An observation run keeps the source URL of its first day; a new URL
  with the same values no longer starts a run. No existing run changed.
- New generated file `llm_ledger_benchmarks.csv`: Epoch AI Benchmarking
  Hub results on ledger models, 3,785 rows for 245 models across 59
  benchmarks, scores copied unchanged with the evaluated model version.
  Benchmarks with no declared score column are left out; Epoch rows
  sourced from Artificial Analysis (226, all SciCode) are dropped because
  its terms forbid redistribution.
- New generated file `llm_ledger_arena.csv`: LMArena's overall-category
  ratings for the text, text with style control, webdev and vision arenas
  on every published leaderboard from 2023-05-08 to 2026-10-27, 60,449
  rows for 253 ledger models (541 arena names). Effort qualifiers fold
  onto their model; names the ledger holds as one model but the arena
  splits into two snapshots (Claude 3.5 Sonnet) stay out. The dataset is
  pulled at a pinned revision and only when its card states CC BY 4.0.
- FIG. 10 gains an Arena rating view: the highest-rated US and Chinese
  ledger model on each LMArena text leaderboard (style control). Both
  files are in the Science bundle and the site's downloads.
- Top-ten arena names since 2025 that stay unjoined: preview and beta
  tags and version suffixes the matcher does not fold
  (`gpt-4.5-preview-2025-02-27`, `grok-3-preview-02-24`, `grok-4.20-beta1`,
  `gemini-1.5-pro-002`), rolling aliases (`chatgpt-4o-latest-20250326`,
  `gpt-5.2-chat-latest-20260210`), a name with no single ledger model
  (`muse-spark`; the ledger holds 1.1 to 1.3), and models the ledger does
  not hold (`o1-mini`, `qwen2.5-max`).

## 2026-10-27

- Bounds now have a direction in `pipeline/confidence.py`. Hub, ModelScope
  and vendor-registry creation times are lower bounds (the release is at
  or after them); a first public Wayback capture is an upper bound. A row
  is `verified` by agreement only when a stated date is among the agreeing
  claims, or a lower bound is closed by an upper bound within two days.
  Two lower bounds that agree stay `inferred`. Before this, a Hub repo and
  its ModelScope twin created the same day verified a release: MiniMax M3.1
  Flash read `verified` 2026-10-17 while its weights were still private on
  2026-10-22. 110 `weights_released` rows move from `verified` to
  `inferred`; no date changes.
- Validation rule 15: an `open_weights` model with `license_family =
  proprietary` is an error; open-weight models with no family are counted
  as a warning and in `coverage_report.md`. 64 models broke the rule. The
  cause: a catalog-only model is drafted `api_only` with license
  `proprietary`, and when its weights later appear the build flipped the
  access type but kept the default license. The Hub census now takes the
  repo's license tag for such machine-owned rows, and the build clears the
  default when no repo states the terms. Of the 64, 35 now carry the
  repo's license (the DeepSeek R1 distills MIT, gpt-oss-safeguard
  Apache-2.0, Hermes 3 the Llama 3 license) and 29 are blank (no Hub repo,
  or the tag is `other`). The same pass gave 93 machine-owned models with
  no license on record their repo's tag. Open-weight models with no
  family: 484 before, 434 after.
- DeepSeek V4 Flash read 2026-10-17 and V4 Flash Vision Exp the same day:
  DeepSeek's own catalog entries `deepseek-v4-flash` and
  `deepseek-v4-flash-vision-exp` are serving aliases that now route to
  V4.1 Flash 1017 (DeepSeek API docs: the legacy names "are still
  accepted, but the corresponding models have been retired"), and the
  vendor entry outvoted every reseller. Such vendor entries no longer vote
  (`match.VENDOR_ALIAS_KEYS`). V4 Flash now reads 2026-04-24 and Vision
  Exp 2026-08-21; each carries an `alias_repointed` row on 2026-10-17. The
  dated snapshots the catalogs folded into their parents are split out:
  `deepseek-v4-flash-0731` (Hub 2026-07-31) and `deepseek-v4-1-flash-1017`
  (Hub 2026-10-17), each `snapshot_of` its parent.
- New labs: Reflection AI (Beam 1.0), Nex AGI (Nex-N2 and N2.5; the
  2026-10-14 dismissal is reversed in `review_decisions.csv`) and Marin
  (marin-8b, marin-32b and the Delphi scaling suite, kept as the Pythia
  suite is). Meta's `meta-models` Hub namespace now counts as Meta, which
  adds the Muse Spark Open repo to the existing model and Muse Glimmer 30B
  Assistant.
- Licenses read from Hub cards where the tag said `other`: GLM-5.3
  `glm-5.3`, MiniMax M3 and M3.1 Flash `minimax-community`, Muse Spark Open
  `muse-model-license` (usage thresholds and a separate agreement per
  their terms), Qwen3.8 2.4T `qwen3.8-max` and Qwen3.8-Flash-Next
  `qwen-community-1.0` (custom, not Apache-2.0), Gemma 4 E2B and E4B
  Apache-2.0, MiMo-V2.6 Pro and Flash MIT.
- MiMo-V2.6 lineage from the report (arXiv:2610.11959, figure 13): each RL
  checkpoint is the base of its MOPD checkpoint, which is the base of the
  released model.
- New column `observed_on` on `events.csv` and `claims.csv`: the day the
  ledger first recorded the row, separate from the date the row states.
  Backfilled by replaying the 64 commits that touched either table: each
  row takes the day of the first commit holding its key (`event_id`; for
  claims `event_id, source_url, date`). Daily pulls commit on the day they
  fetch, so for machine rows this is the manifest's `fetched_at` day; rows
  present at the first publication read 2026-08-25 (events) or 2026-09-01
  (claims, when that table was introduced). A row whose model was renamed
  or merged carries the day of the rename. Eight claims were committed
  after the day they were read (the o1 and o3 Azure retirements,
  reconstructed from raw snapshots on 2026-09-14): their 10-21 statements
  read 2026-09-11, the pull before the move, and the 11-19 statements
  read on the day each source moved (Azure 09-12, LiteLLM 09-13).
  Validation rule 8 now requires `observed_on` and rejects a claim
  superseded before it was observed. Loaders keep the first day
  while a source repeats a statement; agent rows carry the day the feed
  was read. No date or confidence changes.
- New `data/observations/`: `availability_observations.csv`,
  `price_observations.csv` and `capability_observations.csv`, written by
  `pipeline/observe.py`. Each row is a run of days on which one source
  listed one id with the same values (models.dev per provider, OpenRouter,
  LiteLLM, and the OpenAI, Anthropic, Google and Mistral model APIs).
  Backfilled from the 25 archived daily snapshots, 2026-10-03 to
  2026-10-27: 10,472 availability, 16,428 price and 15,928 capability
  runs; 7,231, 10,728 and 9,974 of them resolve to a ledger model. The
  plan counted 53 archives; releases exist only from 2026-10-03, so
  history before that day is manifests only and cannot be rebuilt. The
  daily run now appends. Validation rule 16 checks run bounds, model ids
  and overlaps.
- New generated view `market_on_date.csv` and `pipeline/market.py --date
  D`: every listing of a ledger model on one day with its provider,
  price in USD per 1M tokens, limits and source. On 2026-10-27: 6,698
  listings of 429 models from 203 providers. The site has a market page
  that rebuilds the view for any observed day.
- New `license_family` value `permissive`: terms that grant use without
  restriction but are not OSI-approved. OpenMDW-1.1 (Laguna S 2.1,
  Laguna S 2.1 Base, Laguna XS 2.1, Nemotron Parse 2.0) and CC-BY-4.0
  (Helium 1 Preview 2B) move there from `open_weights_restricted`; CC0-1.0
  moves out of the OSI set, which never approved it (no model carries it).
- New `models.csv` columns `license_has_branding_clause`,
  `license_has_use_restrictions`, `training_data_released` and
  `training_code_released`, blank until read from the card and license
  text. Filled for 109 models of the fully open families: OLMo, OLMo 2,
  OLMoE, Olmo 3 and Olmo Hybrid, Pythia, SmolLM2 and SmolLM3 (data and
  code `true`); Marin (data `partial`: `bigcode/starcoderdata` is gated);
  BLOOM and BLOOMZ (data `partial`: the 224 ROOTS datasets are gated; RAIL
  use restrictions); Tulu 3 on Llama 3.1 and Tulu 2 on Llama 2 (data and
  code `partial`, as the base models' are unreleased; Llama 3.1 has a
  branding clause, both have an acceptable-use policy). Tulu 2 7B gains
  the license its card states, AI2 ImpACT Low-risk. The sources are in
  each row's `notes`.
- New event types `license_changed` (`old->new` in `detail`) and
  `version_observed` (the Hub revision or API snapshot id). New
  `events.csv` column `replacement_model_id`, allowed on
  `deprecation_announced` and `retired`: the 12 `retired` rows that held
  `migration_target_id=` in `detail` move it to the column, and their
  `deprecation_announced` rows from the same deprecation page take the
  same replacement.
- New `data/observations/model_versions.csv`: the version a source states
  for an id, as runs of days. Backfilled from the 25 archives: 104 runs
  (OpenAI and Anthropic dated snapshot ids, Google's `version` field), 53
  of them on a ledger model; no id changed version in that window. The
  Hub puller now records each repo's commit `sha` and `lastModified`, so
  Hub revisions start with the next daily pull; the archived sweeps never
  held them. `observe.py` now tracks the last folded day per table and
  source, so a new table backfills from archives the others already hold.
- The Hub census fills `base_model_id` from a repo's `base_model:` tags
  when every tagged base resolves through the crosswalk to one ledger
  model, the row is not curated, has no base yet, and the link closes no
  cycle. 275 models gain a base; open-weight models with a base go from 6
  to 281 of 1,599.
- New `data/generated/price_changes.csv`: every price change a source
  showed for a ledger-model id, from successive price runs that differ
  (a run broken only by a missed pull is not a change), with a
  `first_party` flag for the maker's own price. These are not written to
  `events.csv` as `price_changed`: of the 40 first-party changes in the
  archive window, most are Zhipu, StepFun and Alibaba catalog entries
  moving together on 2026-10-20/21, which reads as currency conversion
  or newly listed cached prices in the catalog rather than a price the
  vendor announced.
- Retirements carry their replacement. `pull_lifecycle.py` now keeps the
  Azure schedule's `Replacement` column, and `lifecycle.py` writes it to
  `replacement_model_id` when it names exactly one ledger model for the
  version that retires last: 14 Azure `retired` rows (o1, o3, o3-pro and
  o1-pro to GPT-5.6 Sol; o3-mini and o4-mini to GPT-5.6 Terra; GPT-4o to
  GPT-5.1; Grok 3 to Grok 4; DeepSeek R1 to V4 Pro). The agent's page
  extractor asks for the named replacement on deprecation and retirement
  events and keeps it only when it resolves to a ledger model.
- `build.py` queues `predecessor_lead` review rows from family version
  order (115 today); `predecessor_id` stays a person's call.
- Coverage of the dated disclosures. 25 `system_card` rows (7 before)
  from Anthropic's system-card index, at month precision, for the 22
  cards whose name maps to ledger models: Claude 2 through Haiku 5.5
  (the Claude 3 card covers Opus, Sonnet and Haiku). Not mapped: Mythos
  5.1 (not in the ledger), "Mythos Preview" and "Sonnet 3.5 (new)". The
  agent now watches that index for new cards. `pull_arxiv.py` with no
  argument is a daily sweep (in the agent's pulls) that searches arXiv
  titles for the 1,025 dated families with no `paper_published` event,
  40 a day in rotation, and queues `paper_lead` rows for titles that name
  the family ("Gemma 3 Technical Report", "Kimi K2: Open Agentic
  Intelligence") inside the release window; the first run queued one
  (SenseNova-MARS). `pull_nhlocal.py` also queues an `announce_lead` for
  each ledger model with no `announced` event that the timeline names
  (19 today).
- New generated file `llm_ledger_capability.csv`: the Epoch Capabilities
  Index (CC BY 4.0, `pull_capability.py`, in the agent's pulls) joined to
  ledger models, 170 rows (149 by Epoch crosswalk id, 21 by name). ECI
  has no index version or evaluation date; `eci_snapshot_date` stamps the
  scores file. Never copied into core: validation rule 10 now also bans
  `eci_` and `benchmark` columns there. Artificial Analysis is not used;
  its terms forbid redistribution. The site's FIG. 07 plots the best
  open-weights and best API-only score by ledger release date: the best
  open model (Kimi K3, 2026-07-16) scores what an API-only model (GPT-5.4
  Pro) first reached 133 days earlier.
- Ministral 3B corrected from `open_weights` to `api_only` (license
  proprietary). Mistral's launch post (2024-10-16) lists it only as
  `ministral-3b-latest` under the Mistral Commercial License; the
  research weights it mentions are Ministral 8B Instruct's. The models.dev
  reseller vote had dated a `weights_released` 2024-10-22; that row is
  gone, and `announced` and `api_ga` 2024-10-16 now cite the post.
  `reconcile.py` no longer drafts a `weights_released` row for a model a
  person ruled closed; the catalog date folds into `api_ga`.
- New observation table `research_mentions.csv`
  (`pull_research_mentions.py`, in the agent's pulls): arXiv titles and
  abstracts from OAI-PMH (cs.AI, cs.CL, cs.CV, cs.LG, stat.ML, CC0
  metadata) matched against the ledger's own spellings, one row per paper
  version and model or family named. The backfill read papers modified
  since 2023-01-01: 38,227 rows from 23,598 papers (28,553 name a model,
  9,674 only a family). Matching is deterministic and conservative: a
  spelling needs a version or size, punctuation breaks it, and "word +
  number" must be capitalized, so "step 3" and bare "Qwen" are not
  counted; counts are a floor. Validation rule 17 checks the table.
- New generated files `research_mentions_monthly.csv` (papers per family
  per month) and `research_first_mentions.csv` (each model's first paper
  beside its weights and availability dates). 584 models have a first
  mention; the median `days_to_first_mention` is 88 for open-weight
  models (426) and 20 for API-only models (139). Negative values flag
  dates to review: Llama 3 8B Instruct reads 2024-07-23 (a models.dev
  date over a 2024-04-17 Hub repo) and Llama 2 70B has no
  `weights_released` row. The site's FIG. 08 bins these days by access
  type, and its download menu now lists the observation, capability and
  research files.
- The site splits models three ways: fully open (OSI-approved or
  permissive license, training data and code released; 88 models), other
  open weights, and API only, in every figure and as an explorer filter.
  New FIG. 09 shows open-weight models by year from fully open to no
  recorded license (5% fully open, 55% open license without released
  data and code on record, 13% restricted, 26% unrecorded). New FIG. 10
  compares US and Chinese developers: models per year (702 US, 77% open
  weights; 606 Chinese, 91% open weights) and the best ECI score over
  time (the best Chinese model, Kimi K3, scores what GPT-5.4 Pro first
  reached 133 days earlier).
- The explorer filters by developer country (headquarters, from
  `organizations.country`; "Not recorded" for BigScience, Nex AGI and
  RWKV), and its CSV export carries a `developer_country` column.
- `docs/erd.svg` shows the columns added this month (`models`: the
  branding and use-restriction flags, `training_data_released`,
  `training_code_released`; `events`: `observed_on`,
  `replacement_model_id`; `claims`: `observed_on`).
- `make bundles` (`pipeline/bundles.py`) writes four zips to
  `dist/bundles/`: Markets, Science, Lineage and Governance. Each holds
  `models.csv`, `organizations.csv`, its tables, the `events.csv` rows of
  its event types with their `claims.csv` rows, a methods page
  (`docs/bundles/<name>.md`) and the license. Bundles copy rows and add
  no storage, so ids agree across them.

## 2026-10-14

- Meta's original `codellama` Hub namespace now counts as Meta. Code Llama
  7B, 7B Instruct, 7B Python, 13B Instruct and 34B Instruct read 2024-03,
  when Meta re-created the repos under `meta-llama`; their original repos
  are pinned in the crosswalk, so they read 2023-08-24, the launch day.
  Code Llama 13B (base) is added.
- A model listed by two catalogs under a vendor that maps to no lab was
  dropped without trace; each such vendor is now a
  `catalog_unmapped_vendor` review lead, the API-side twin of
  `hf_unmapped_namespace`, so a new API-only lab is noticed.
- From its first leads: Perceptron (US), Motif Technologies (KR) and
  Xiaohongshu (CN, the Dots Studio models) are added as labs, and
  LLM360 and IFM (K2 Think) count as MBZUAI. The other twenty vendors,
  fine-tune shops, routers and tool or embedding endpoints, are dismissed
  in `review_decisions.csv`.

## 2026-10-03

- 28 labs added to the sweep: LG AI Research, NAVER, Kakao, Upstage,
  Sakana AI, Preferred Networks, rinna, Aleph Alpha, Kyutai, Swiss AI,
  Sber, Yandex, MBZUAI, Sarvam, SenseTime, Kuaishou, Apple, Salesforce,
  ServiceNow, Arcee, Prime Intellect, Zyphra, Writer, Inception Labs,
  Thinking Machines, Poolside, BigScience and TinyLlama; Meta's older
  `facebook` Hub namespace now counts as Meta.
- The Hub sweep had dropped 57 of Mistral's 60 repos, Magistral among
  them: Mistral's own-format weights carry no pipeline tag. An untagged
  repo that declares vLLM serving now counts. Hub repos that repeat a
  Mistral model already on record under its API name are pinned to that
  model in the crosswalk. Intermediate training checkpoints and `-vllm`,
  `-fp8-block` and Petals repackagings are not separate models.
- Llama 3.1 405B Instruct read 2026-09-10, a single reseller's listing that
  models.dev called a weights release; it now reads 2024-07-23, the
  Bedrock and Vertex launch a person verified. An unverified first
  availability more than 180 days after the announcement gives way to an
  earlier person-verified launch, and otherwise goes to the review queue
  as `long_announce_gap`.

- Validation rule 4 pairs `deprecation_announced` with `retired` within one
  platform scope. LiteLLM began listing Azure's 2025-06-06 retirement of
  GPT-4 on 2026-09-25; compared against OpenAI's own 2026-04-22 deprecation
  notice (global scope) it read as "announced after retired" and the daily
  run refused to publish from 2026-09-25 to 2026-10-02. No row changed by
  the rule itself; the missed days are caught up by the 2026-10-03 update
  (raw snapshots for those days were not kept).
- Churn guard in `pipeline/validate.py`: a run that removes more than 2% of
  the committed events, or re-dates more than 5%, is refused unless run with
  `--allow-churn`. The daily job now also archives each day's raw pull
  privately even when a later step fails, opens an issue when a run fails,
  and judges each agent row on its own so one bad extraction no longer
  holds back the others.
- Publishing rule for rows the page-reading agent writes
  (`verified_by=llm-ledger-agent`): a row whose date agrees with the
  machine claims already on record replaces that row as `verified`; a row
  with no other source is published as `inferred`. A catalog that later
  lists the same date upgrades it to `verified`. The agent may now create a
  model it read about before any catalog listed it, only from a launch
  event whose quote names the model and whose name is not a product or a
  bare family name. Such a model is withdrawn, with a line here, if no
  catalog, Hub repo or vendor API lists it within 60 days.
- Agent rows no longer count as `curated` in the coverage report or the
  README (that word now means a person checked the page), and the loaders
  fill in family, variant and access type for agent-found models. One
  model moves from curated to corroborated (`north-mini-code`). The
  coverage report gains a section on what the agent wrote and declined.
- The agent reads each new post on a vendor's blog index as its own page,
  extracts with a fixed output schema and a rule that products, plans and
  customer stories are not model events, and stops at $1 a run or $30 a
  month. Every refusal is counted by reason in `data/agent_declined.csv`.
  Its extraction precision is measured on pages it read before and is
  published in `docs/methodology.md`.
- `Meta Superintelligence Labs` is an alias of `meta`, so posts signed by
  the lab count as Meta's own.
- The README stats paragraph opens with the date of the latest source
  pull.

## 2026-09-14

- `north-mini-code-announced-1`: source_url corrected from the Cohere blog
  index to the post (`cohere.com/blog/north-mini-code`, dated 2026-06-09).
  The agent read the event off the index page; it now cites the post
  whose headline the evidence quote opens with.
- Lifecycle loader resolves a platform's model id through the crosswalk
  first (exact id), then by name; when the two name different models the
  row goes to the review queue as `lifecycle_ambiguous` instead of being
  guessed. Azure's `o1-2024-12-17` and `o3-2025-04-16` were unresolved by
  name alone (the ids are `openai-o1`, `openai-o3`); their Azure
  retirements are now recorded, with the 09-12 Azure move
  (2026-10-21 to 2026-11-19) and LiteLLM's 09-13 follow-up backfilled as
  superseded claims from the raw snapshots.
- Azure Foundry's partner-served `FW-` SKUs (Fireworks AI) resolve to the
  model they serve; the event stays on `platform=azure` and `detail`
  records `served_by=Fireworks AI (<sku>)`. 12 `retired` events added;
  where Azure lists a native and a partner SKU of one model
  (DeepSeek-V3.1, Kimi-K2.5) the event now carries the later partner date
  under the existing last-version rule. Those two date changes are the
  resolver's, not Azure's, so no superseded claim was written for them.

## 2026-09-13 (v2026.10)

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
- Licensing files reorganised: `LICENSE` is now the CC BY 4.0 legal code
  verbatim (the dataset), `pipeline/LICENSE` the MIT text (the code);
  the pointer file and the paraphrased `LICENSE-DATA` are gone. Terms,
  upstream attribution and the citation request live in the README.
  Correction: NHLOCAL/AiTimeline is MIT-licensed, not CC BY 4.0 as the
  old file said. `docs/sources.md` gains a Terms column naming the license
  or terms every script-pulled source is used under.
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

## 2026-09-14

- `north-mini-code-announced-1` 2026-06-09 verified (vendor_blog; evidence: "Introducing North Mini Code: Cohere’s first model for developers"; agrees: epoch.ai 2026-06-09)

## 2026-10-05

- new model `rerank-v3-5`
- `rerank-v3-5-announced-1` 2024-12-02 inferred (deprecation_page; evidence: "On December 2nd, 2024, we announced the release of Rerank-v3.5 along with the deprecation of the Rerank-v2.0 model family.")

## 2026-10-06

- new model `mistral-large-4`
- `glm-5-3-platform_availability-2` 2026-10-05 inferred (vendor_blog; evidence: "GLM 5.3 from Z.ai (Zhipu AI) is now available on Amazon Bedrock .")
- `mistral-large-4-announced-1` 2026-10-06 inferred (vendor_blog; evidence: "Today, we’re launching a public preview of Mistral Large 4.")

## 2026-10-08

- `gpt-6-sol-consumer_rollout-1` 2026-10-07 inferred (vendor_blog; evidence: "GPT‑6 in ChatGPT is powered by GPT‑6 Sol for Plus, Pro, Business, and Enterprise tiers")
- `claude-haiku-5-5-platform_availability-2` 2026-10-07 inferred (vendor_blog; evidence: "Today, we’re excited to announce the availability of Claude Haiku 5.5 on Amazon Bedrock and Claude Platform on AWS .")

## 2026-10-13

- `gemini-3-6-flash-consumer_rollout-1` 2026-07-21 inferred (vendor_changelog; evidence: "We’re introducing Gemini 3.6 Flash, an upgraded version of our Flash model... We're excited to bring this model to all Gemini app users globally.")
- `gemini-3-5-flash-consumer_rollout-1` 2026-05-19 inferred (vendor_changelog; evidence: "Gemini 3.5 Flash is our best model yet for getting challenging tasks done quickly and efficiently... Rolling out to everyone globally.")
- `gemini-3-1-pro-consumer_rollout-1` 2026-02-19 inferred (vendor_changelog; evidence: "3.1 Pro is rolling out globally to the Gemini app, with higher limits for users with Google AI Pro and Ultra plans.")
- `gemini-3-flash-consumer_rollout-1` 2025-12-17 inferred (vendor_changelog; evidence: "Gemini 3 Flash is now the new default model in the Gemini app.")
- `gemini-3-pro-consumer_rollout-1` 2025-11-18 inferred (vendor_changelog; evidence: "Gemini 3 Pro is rolling out to everyone in the Gemini app starting today, with higher limits for users in the Google AI Plus, Pro & Ultra plans.")

## 2026-10-14

- `gemini-4-argon-api_ga-1` 2026-10-13 verified (vendor_blog; evidence: "Gemini 4 Argon is now globally available today for developers and enterprises via the API in AI Studio and Gemini platform"; agrees: models.dev (firs)
- `gemini-4-argon-consumer_rollout-1` 2026-10-13 inferred (vendor_blog; evidence: "For everyday users: Try it starting today in the Gemini app and AI Mode in Search if you’re a Google AI Ultra or Pro subscriber.")
- `gemini-4-argon-price_changed-1` 2026-10-13 inferred (vendor_blog; evidence: "The model launches today at an introductory price 1 of $2 per million input tokens and $10 per million output tokens")
- `grok-4-7-platform_availability-2` 2026-10-13 inferred (vendor_blog; evidence: "SpaceXAI’s Grok 4.7 is now available on Amazon Bedrock, which offers a choice of foundation models (FMs) from multiple providers.")

## 2026-10-21

- new model `claude-mythos`
- new model `fable-5-1`
- new model `voxtral-small-transcribe-3`
- new model `voxtral-mini-tts-3`
- new model `voxtral-mini-transcribe-3`
- new model `voxtral-mini-transcribe-realtime-3`
- `claude-haiku-5-5-announced-1` 2026-10-07 inferred (vendor_blog; evidence: "Introducing Claude Haiku 5.5 Claude Haiku 5.5 is our fastest, most capable small model.")
- `claude-sonnet-5-5-announced-1` 2026-09-28 verified (vendor_blog; evidence: "Introducing Claude Sonnet 5.5 Claude Sonnet 5.5 is a clear upgrade over Claude Sonnet 5, runs 30%+ faster"; agrees: epoch.ai 2026-09-28)
- `claude-opus-5-5-announced-1` 2026-09-22 inferred (vendor_blog; evidence: "Introducing Claude Opus 5.5 Claude Opus 5.5 leads in agentic coding and knowledge work")
- `claude-mythos-announced-1` 2026-09-15 inferred (vendor_blog; evidence: "Introducing Claude Mythos and Fable 5.1 They’re the world’s most advanced models for coding and knowledge work")
- `fable-5-1-announced-1` 2026-09-15 inferred (vendor_blog; evidence: "Introducing Claude Mythos and Fable 5.1 They’re the world’s most advanced models for coding and knowledge work")
- `voxtral-small-transcribe-3-announced-1` 2026-10-20 inferred (vendor_blog; evidence: "The speech-to-text model, Voxtral Small Transcribe 3 , is state-of-the-art in multilingual transcription")
- `voxtral-mini-tts-3-announced-1` 2026-10-20 inferred (vendor_blog; evidence: "The text-to-speech model, Voxtral Mini TTS 3 , introduces new voices that adjust their emotion, pace, and emphasis")
- `voxtral-mini-transcribe-3-announced-1` 2026-10-20 inferred (vendor_blog; evidence: "Voxtral Mini Transcribe 3 New Efficient, low-latency speech transcription model.")
- `voxtral-mini-transcribe-realtime-3-announced-1` 2026-10-20 inferred (vendor_blog; evidence: "Voxtral Mini Transcribe Realtime 3 listens and detects when the caller has finished speaking")

## 2026-10-22

- new model `cohere-transcribe-arabic`
- new model `cohere-transcribe`
- `cohere-transcribe-arabic-announced-1` 2026-07-07 inferred (vendor_blog; evidence: "Today, we are releasing Cohere Transcribe Arabic as an open-source model.")
- `cohere-transcribe-arabic-api_ga-1` 2026-07-07 inferred (vendor_blog; evidence: "Cohere Transcribe Arabic is also available through the Cohere API with free access subject to rate limits.")
- `cohere-transcribe-announced-1` 2026-03-01 inferred (vendor_blog; evidence: "We started with Cohere Transcribe (launched in March with leading English-language accuracy and broad multilingual coverage)")

## 2026-10-27

- `gpt-6-1-terra-announced-1` 2026-10-26 inferred (vendor_blog; evidence: "We’re introducing GPT-6.1 Terra , a fast, efficient model that combines detailed visual reasoning and precise computer use alongside clearer, more na)
- `gpt-6-1-terra-consumer_rollout-1` 2026-10-26 inferred (vendor_blog; evidence: "Starting today, GPT-6.1 Terra is available to all Plus, Pro, Enterprise, and Edu users in ChatGPT Work and Codex.")
- `gpt-6-1-terra-system_card-1` 2026-10-26 inferred (vendor_blog; evidence: "More detail is available in the system card")
