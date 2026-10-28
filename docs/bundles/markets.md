# Markets bundle: methods

Question: on a given day, which models could you call, from which
provider, at what price and with what limits, and when did a provider
start or stop offering one?

## Files

| File | What a row is |
|---|---|
| `availability_observations.csv` | a run of days on which a source listed an id; its first and last day are a provider's observed entry and exit |
| `price_observations.csv` | a run of days on which a source showed one price for an id, in the source's own unit |
| `capability_observations.csv` | a run of days with one context length, output limit, modality set and tool flag |
| `market_on_date.csv` | every listing of a ledger model on the newest observed day, with that day's price and limits (USD per 1M tokens) |
| `price_changes.csv` | two successive price runs of one id with different prices |
| `attributes.csv` | one current serving snapshot per model (context, modalities, list price) |
| `events.csv` | dated availability, price and retirement events: `api_preview`, `api_ga`, `free_tier`, `consumer_rollout`, `platform_availability`, `price_changed`, `retired` |
| `claims.csv` | every source statement behind those events |
| `models.csv`, `organizations.csv` | the identifiers every other file uses |

## How the rows are made

Observations are copied from the daily pulls of models.dev, OpenRouter,
LiteLLM and the vendor model APIs, folded into runs by
`pipeline/observe.py`. A day nobody pulled ends every run, so a run never
spans an unobserved day; an id missing on a pulled day was not listed.
`model_id` is resolved through `crosswalk.csv` and is blank when an id
names no ledger model. Events are conclusions drawn from claims under the
confidence rules in `docs/methodology.md`; a provider's own date is
first-party evidence for that provider's event only.

## Limits

- Observation coverage starts 2026-10-03, the oldest archived raw
  snapshot. Entry before that day is the event record, not an observation.
- A listing is what an aggregator shows, not proof a request succeeds.
- Prices are list prices; discounts, batch and regional prices are absent.
- `price_changes.csv` is catalog diffs. A `price_changed` event needs the
  vendor's own page; currency conversion and newly listed cached prices
  show up as changes in the diffs.

Column definitions: `docs/schema.md`, sections "data/observations/" and
"Generated artifacts". Data is CC BY 4.0 (see `LICENSE`).
