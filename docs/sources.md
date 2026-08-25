# Sources

We save facts and URLs. We do not copy article text except a short
quote when we need evidence.

## Tier 1: scripts

Snapshots go under `data/raw/{source}/{date}/`. We commit a manifest
(URL + sha256), not the dump.

| Source | Endpoint | What we take |
|---|---|---|
| models.dev | `https://models.dev/api.json` | claimed release date, context, price |
| OpenRouter | `https://openrouter.ai/api/v1/models` | listing date (`created`), slugs |
| OpenAI / Anthropic / Google / Mistral | vendor APIs | listing and shutdown fields (need keys) |
| Hugging Face Hub | `huggingface_hub` | `createdAt`, license, tags |
| ModelScope | OpenAPI | Chinese Hub metadata (needs OAuth) |
| arXiv | export API | paper v1 date |
| Epoch AI | `https://epoch.ai/data/all_ai_models.csv` | enrichment join only |

Pullers with no key just skip. No fake rows.

## Tier 2: primary pages

Vendor blogs, changelogs (often better than blogs), deprecation pages
(best for shutdowns), model cards, GitHub tags, pricing pages.

## Tier 3: leads only

Community timelines (NHLOCAL/AiTimeline, Physics-Lee), Wikipedia,
HF collections, host catalogs. These go to
`data/staging/review_queue.csv`. They are not truth until tier 2
confirms them.

## Tier 4: archives

Wayback first capture, arXiv v1 vs later versions, first HN /
r/LocalLLaMA posts, vendor posts on X.

## Tier 5: papers

Appendix calendars. `source_type=published_paper`.

## Which source for which event

| Event | First try | Fallback |
|---|---|---|
| `announced` | vendor blog | Wayback, vendor post |
| `paper_published` | arXiv v1 | proceedings |
| `system_card` | vendor site | Wayback |
| `api_preview` / `api_ga` | vendor changelog | OpenRouter, models.dev |
| `weights_released` | HF `createdAt` | ModelScope, GitHub tag |
| `consumer_rollout` / `free_tier` | vendor blog | Wikipedia, then check |
| `platform_availability` | Azure / AWS / GCP changelog | platform blog |
| `price_changed` | pricing page + Wayback | news |
| `deprecation_announced` / `retired` | deprecation page | OpenRouter expiration |
| attributes | vendor docs | typed from those docs |

## Quirks

- HF `createdAt` = 2022-03-02 is a backfill. Never a weights date.
- OpenRouter `created` is when *they* listed the model, often late.
  We store it as `inferred`.
- Vendor blogs sometimes get a new date later. Check Wayback if it
  looks wrong.
