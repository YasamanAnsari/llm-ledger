# Sources

We save facts and URLs. We do not copy article text except a short
quote when we need evidence.

## Tier 1: scripts

Snapshots go under `data/raw/{source}/{date}/`. We commit a manifest
(URL + sha256), not the dump.

| Source | Endpoint | What we take | Role |
|---|---|---|---|
| models.dev | `https://models.dev/api.json` | release date, open-weights flag, context, price, modalities | stated date; attributes |
| OpenRouter | `https://openrouter.ai/api/v1/models` | listing date (`created`), expiration | first-party for `platform_availability` on OpenRouter |
| OpenAI / Anthropic / Google / Mistral | vendor `/models` APIs | `created` (registry timestamp), `shutdown_date`, ids | `created` is a bound; `shutdown_date` is first-party `retired` (need keys) |
| Hugging Face Hub | `huggingface_hub` | `createdAt`, license, tags | bound for `weights_released` |
| Internet Archive | `archive.org/wayback/available` | first public capture of the repo page | bound that corroborates `createdAt` |
| Azure Foundry | model retirement schedule page | version dates, retirement dates | first-party `retired` on `azure` |
| Amazon Bedrock | model lifecycle page | EOL dates | first-party `retired` on `bedrock` |
| LiteLLM | `model_prices_and_context_window.json` | `deprecation_date` | corroborates retirements |
| Epoch AI | `https://epoch.ai/data/all_ai_models.csv` | publication date; scale columns | `announced` claim; enrichment join |
| ModelScope | OpenAPI | Chinese Hub metadata (needs OAuth) | |
| arXiv | export API | paper v1 date | lookup tool for `paper_published` |

Pullers with no key just skip. No fake rows. Every machine claim a row
rests on is kept in `data/core/claims.csv`.

## Tier 2: primary pages

Vendor blogs, changelogs (often better than blogs), deprecation pages
(best for shutdowns), model cards, GitHub tags, pricing pages.

## Tier 3: leads only

Community timelines (NHLOCAL/AiTimeline, Physics-Lee), Wikipedia,
HF collections, host catalogs. These go to
`data/staging/review_queue.csv`. They are not truth until tier 2
confirms them.

## Tier 4: archives

Wayback first capture (automated for Hub repos, manual elsewhere), arXiv
v1 vs later versions, first HN / r/LocalLLaMA posts, vendor posts on X.

## Tier 5: papers

Appendix calendars. `source_type=published_paper`.

## Which source for which event

| Event | First try | Fallback |
|---|---|---|
| `announced` | vendor blog | Wayback, vendor post |
| `paper_published` | arXiv v1 | proceedings |
| `system_card` | vendor site | Wayback |
| `api_preview` / `api_ga` | vendor changelog | models.dev, corroborated by the vendor API `created` |
| `weights_released` | vendor announcement | models.dev open-weights date; HF `createdAt` corroborated by Wayback |
| `consumer_rollout` / `free_tier` | vendor blog | Wikipedia, then check |
| `platform_availability` | platform's own listing (OpenRouter `created`) | Azure / AWS / GCP changelog |
| `price_changed` | pricing page + Wayback | news |
| `deprecation_announced` / `retired` | deprecation page | vendor `shutdown_date`, Azure / Bedrock schedules, LiteLLM, OpenRouter expiration |
| attributes | vendor docs | models.dev |

## Quirks

- HF `createdAt` = 2022-03-02 is a backfill. Never a weights date.
- HF `createdAt` in general precedes the public launch (repos are created
  private). It is a bound: it corroborates, it does not date.
- OpenAI and Anthropic `created` timestamps precede the launch by 1-16
  days for the same reason. Same treatment.
- OpenRouter `created` is when *they* listed the model. It is the truth
  about the OpenRouter listing, so it is a verified
  `platform_availability`, and nothing more.
- models.dev `release_date` ending in `-01-01` is a year placeholder;
  stored at `precision=year`.
- Wayback first captures lag by months for small repos.
- Vendor blogs sometimes get a new date later. Check Wayback if it
  looks wrong.
