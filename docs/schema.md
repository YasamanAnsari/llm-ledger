# llm-ledger schema

Five core tables plus two generated files. CSVs are UTF-8, LF, sorted by
primary key, ISO dates. The code of record is `pipeline/schema.py`.

## Rules

1. Epoch's size and compute numbers stay out of core. We join them in
   the enrichment file only.
2. Events are rows. A new event type does not need a new column.
3. Every date needs `source_url`, `precision`, and `confidence`.
4. If the source says "April 2023", we store `2023-04-01` and
   `precision=month`. We do not invent a day.
5. If sources disagree, we keep both. We do not pick in silence.
6. Fixes edit the row. `record_created` / `record_updated` and
   `CHANGELOG.md` keep history.
7. Generated files must rebuild the same from the same snapshots.

## Who gets in

A named trained checkpoint from a lab. GGUF, LoRA, and merges stay
out unless the thing is famous on its own. If we keep a derivative,
we set `is_derivative`, `derivative_type`, and `base_model_id`.

## organizations.csv

| Column | Type | Rules |
|---|---|---|
| `org_id` | string PK | slug, stable, never reused (e.g. `alibaba`, `openai`) |
| `canonical_name` | string | e.g. "Alibaba Cloud" |
| `short_name` | string | chart-friendly, e.g. "Alibaba" |
| `aliases` | pipe-separated list | all observed spellings and lab names |
| `parent_org_id` | FK nullable | subsidiaries/labs point to parent |
| `country` | ISO 3166-1 alpha-2 | headquarters; coding aligned with Epoch |
| `org_type` | enum | `big_tech, ai_lab, startup, academic, government, nonprofit` |
| `is_active` | bool (`true`/`false`) | |
| `epoch_org_name` | string nullable | exact organization string used by Epoch, for joining |
| `notes` | string | |

## models.csv

| Column | Type | Rules |
|---|---|---|
| `model_id` | string PK | slug, stable, never reused (e.g. `openai-o3`) |
| `canonical_name` | string | display name |
| `family` | string | e.g. `GPT-5`, `Claude 4`, `Qwen3` |
| `variant_role` | enum | `base, mini, nano, pro, thinking, instruct, chat, coder, vision, other` |
| `developer_org_id` | FK to organizations | |
| `developing_lab` | string nullable | sub-org team, e.g. "FAIR" |
| `co_developer_org_ids` | pipe-list of FKs, nullable | |
| `model_type` | enum | `llm, vlm, multimodal, image_gen, video_gen, audio, embedding` |
| `access_type` | enum | `open_weights, api_only, consumer_only, internal, never_released` |
| `license` | string | exact SPDX identifier or license name |
| `license_family` | enum | `proprietary, open_weights_restricted, osi_approved` |
| `license_has_usage_thresholds` | bool | revenue/user-count clauses |
| `license_requires_separate_agreement` | bool | commercial licence required |
| `is_derivative` | bool | |
| `derivative_type` | enum nullable | `finetune, distill, quantization, merge, continued_pretrain` |
| `base_model_id` | FK nullable | |
| `parent_model_id` | FK nullable | e.g. `openai-o3-pro` points to `openai-o3` |
| `snapshot_of` | FK nullable | dated snapshot points to its alias parent |
| `predecessor_id` / `successor_id` | FK nullable | lineage |
| `first_public_availability_date` | date DERIVED | see derived-field rules |
| `first_availability_via` | enum DERIVED | which event won |
| `anticipation_days` | int DERIVED | first availability minus announced |
| `record_created` / `record_updated` | ISO datetime | |
| `notes` | string | |

Derived columns are recomputed by `pipeline/build.py` on every run and must
never be hand-edited.

## events.csv (the heart of the dataset)

| Column | Type | Rules |
|---|---|---|
| `event_id` | string PK | `{model_id}-{event_type}-{seq}` |
| `model_id` | FK | |
| `event_type` | enum | see event vocabulary below |
| `date` | ISO date | first day of period when precision is coarser than day |
| `precision` | enum | `day, month, quarter, year` |
| `region` | string | default `global`; else ISO country or `EU`/`US`/`CN` |
| `platform` | string | required for, and only allowed on, `platform_availability` |
| `detail` | string nullable | event-type-specific, see below |
| `source_url` | URL | REQUIRED; the page actually consulted |
| `source_type` | enum | `vendor_blog, vendor_docs, vendor_changelog, deprecation_page, system_card, arxiv, hf_hub, github, modelscope, api_metadata, news, wikipedia, community_timeline, published_paper, wayback` |
| `confidence` | enum | `verified, inferred, disputed` |
| `verified_by` | string | required when `confidence=verified` |
| `verified_date` | date | required when `confidence=verified` |
| `notes` | string | REQUIRED when `confidence=disputed`: all conflicting values and sources |

`detail` conventions:

- `feature_added`: one of `vision, voice, tool_use, long_context,
  web_browsing, file_upload, structured_output`.
- `price_changed`: `input:old->new;output:old->new` in USD per 1M tokens.
- `renamed`: `old->new`.
- `retired`: optional `migration_target_id=<model_id>`.

## Event type vocabulary

| `event_type` | Definition |
|---|---|
| `announced` | First official public statement of the model's existence |
| `preview` | Limited/waitlist/safety-tester access begins |
| `paper_published` | arXiv **v1** submission date (never a later revision) or proceedings date |
| `system_card` | System/model card published (distinct from the paper) |
| `api_preview` | Available via API in preview/beta |
| `api_ga` | Generally available via the vendor's API |
| `weights_released` | Weights publicly downloadable (HF/ModelScope/GitHub timestamp) |
| `consumer_rollout` | Available in a consumer product to paid users |
| `free_tier` | Available to free-tier consumer users (mass-adoption moment) |
| `platform_availability` | GA on a third-party cloud platform (`platform` required) |
| `price_changed` | Official per-token price change |
| `feature_added` | Capability added to an existing model |
| `alias_repointed` | A vendor alias repointed to a new snapshot |
| `renamed` | Public product/model renamed |
| `deprecation_announced` | Vendor announces future retirement |
| `retired` | Model actually turned off / removed |

Why events, not a single "release date": GPT-3's paper went to arXiv on
May 28, 2020 but the API beta opened June 11, 2020. o3 was announced
December 20, 2024, released in the API April 16, 2025, and o3-pro followed
June 10, 2025. Collapsing these into one undocumented date is how existing
datasets disagree with each other.

## crosswalk.csv

| Column | Type | Rules |
|---|---|---|
| `model_id` | FK | |
| `namespace` | enum | `openrouter, models_dev, huggingface, modelscope, openai_api, anthropic_api, google_api, epoch, wikipedia, lmarena, text_surface_forms` |
| `identifier` | string | the ID/name in that namespace; for `text_surface_forms`, one row per observed human spelling |

Primary key is the full triple, so a model may carry several identifiers per
namespace (e.g. many surface forms).

## attributes.csv (serving + reasoning snapshot; one row per model)

| Column | Type |
|---|---|
| `model_id` | FK |
| `reasoning_type` | `none, always_on, toggleable, effort_tiered` |
| `reasoning_effort_levels` | pipe-list nullable |
| `reasoning_tokens_billed` | bool nullable |
| `reasoning_tokens_visible` | `hidden, summarized, full` nullable |
| `reasoning_is_separate_checkpoint` | bool nullable |
| `context_length` | int |
| `max_output_tokens` | int nullable |
| `modality_in` / `modality_out` | pipe-lists of `text, image, audio, video` |
| `knowledge_cutoff` | ISO date nullable |
| `supports_tool_use` / `supports_structured_output` / `supports_caching` | bool nullable |
| `price_input` / `price_output` / `price_cached_input` | USD per 1M tokens, nullable |
| `price_date` | date the prices were observed |
| `source_url` | URL |

Price *history* lives in `events.csv` as `price_changed` rows; this table
holds only the latest observed snapshot.

## Derived-field computation rules

- `first_public_availability_date` = MIN over global-region events of type
  `{api_ga, weights_released, consumer_rollout}`. If none exist, fall back to
  MIN of `{api_preview, free_tier}` and suffix `first_availability_via` with
  `_fallback`.
- `first_availability_via` = the event type that achieved the minimum; ties
  broken by priority `weights_released > api_ga > consumer_rollout`
  (fallback ties: `api_preview > free_tier`).
- `anticipation_days` = `first_public_availability_date - announced.date`;
  null if either is missing or either precision is coarser than `month`.
- All derived fields are recomputed by `pipeline/build.py` every run.

## Confidence semantics

| `confidence` | Meaning |
|---|---|
| `verified` | The primary source was opened and the date confirmed. `verified_by` and `verified_date` required. |
| `inferred` | Taken from a secondary/aggregator source without primary confirmation. |
| `disputed` | Two or more sources conflict beyond precision differences. All values recorded in `notes`; `date` keeps the best-evidenced value. |

## Generated artifacts (never hand-edited)

- `data/generated/llm_ledger_wide.csv` - one row per model; each event type
  pivoted to `{event_type}_date` + `{event_type}_precision` (global region
  only; repeatable event types pivot to their earliest occurrence), joined
  with models and attributes.
- `data/generated/llm_ledger_enriched.csv` - the wide file LEFT JOINed to an
  Epoch AI snapshot via the crosswalk, carrying Epoch's scale columns and
  confidence labels plus a constant `epoch_snapshot_date` column. Epoch data
  is CC BY 4.0 and credited in LICENSE-DATA and the README.

## Validation rules

`pipeline/validate.py` enforces, and exits nonzero on failure:

1. PK uniqueness on all tables; all FKs resolve.
2. Every event has a valid `source_url`, plus `precision` and `confidence`.
3. `date` is consistent with `precision` (month precision means day == 01,
   quarter means the first day of Jan/Apr/Jul/Oct, year means Jan 1).
4. Temporal sanity per model and region:
   `announced <= preview <= api_preview <= api_ga` where present;
   `deprecation_announced <= retired`; no event after today except `retired`
   rows from announced shutdown schedules (flagged as warnings, not failures).
5. `disputed` implies non-empty `notes`; `verified` implies `verified_by`
   and `verified_date`.
6. Every model has at least one event; every non-derivative model has an
   `announced` or an availability event.
7. `snapshot_of` / `base_model_id` / `parent_model_id` links are acyclic.
8. Controlled-vocabulary columns contain only allowed values.
9. Wide/enriched artifacts regenerate byte-identically from core tables.
10. No Epoch-domain numeric columns (parameters, compute, dataset size,
    training cost) exist in any core table.
