# Treatment-date sensitivity report

How far apart are the candidate 'release dates' of the same model?
Computed from the ledger's own dated events (global region, earliest
event per type, day/month precision as recorded). Gaps are in days;
positive means the second event happened after the first.

## announced -> api_ga

- median 0d (IQR 0-8d, n=119)
- range: 0d to 701d

| gap | models |
|---|---|
| same day | 69 |
| 1-7d | 19 |
| 8-30d | 7 |
| 31-90d | 9 |
| 91-365d | 12 |
| >365d | 3 |

Per-organization medians (n>=3):

- alibaba: 15d (n=9)
- google: 2d (n=17)
- xai: 0d (n=8)
- amazon: 0d (n=3)
- anthropic: 0d (n=15)
- deepseek: 0d (n=4)
- mistral: 0d (n=7)
- bytedance: 0d (n=3)
- zhipu: 0d (n=4)
- openai: 0d (n=33)
- meta: 0d (n=3)

## announced -> weights_released

- median 0d (IQR 0-1d, n=77)
- range: 0d to 185d

| gap | models |
|---|---|
| same day | 55 |
| 1-7d | 14 |
| 8-30d | 1 |
| 31-90d | 1 |
| 91-365d | 6 |
| >365d | 0 |

Per-organization medians (n>=3):

- alibaba: 0d (n=12)
- mistral: 0d (n=5)
- deepseek: 0d (n=9)
- google: 0d (n=7)
- zhipu: 0d (n=7)
- moonshot: 0d (n=5)
- meta: 0d (n=8)
- nvidia: 0d (n=6)
- minimax: 0d (n=5)

## announced -> consumer_rollout

- median 0d (IQR 0-30d, n=23)
- range: 0d to 117d

| gap | models |
|---|---|
| same day | 15 |
| 1-7d | 0 |
| 8-30d | 2 |
| 31-90d | 5 |
| 91-365d | 1 |
| >365d | 0 |

Per-organization medians (n>=3):

- anthropic: 0d (n=6)
- openai: 0d (n=13)

## announced -> free_tier

- median 0d (IQR 0-0d, n=10)
- range: 0d to 72d

| gap | models |
|---|---|
| same day | 7 |
| 1-7d | 0 |
| 8-30d | 0 |
| 31-90d | 3 |
| 91-365d | 0 |
| >365d | 0 |

Per-organization medians (n>=3):

- anthropic: 0d (n=3)
- openai: 0d (n=5)

## api_ga -> free_tier

- median 0d (IQR 0-0d, n=10)
- range: -91d to 63d

| gap | models |
|---|---|
| same day | 7 |
| 1-7d | 1 |
| 8-30d | 0 |
| 31-90d | 1 |
| 91-365d | 1 |
| >365d | 0 |

Per-organization medians (n>=3):

- anthropic: 0d (n=3)
- openai: 0d (n=5)

## consumer_rollout -> free_tier

- median 0d (IQR 0-0d, n=6)
- range: -63d to 0d

| gap | models |
|---|---|
| same day | 5 |
| 1-7d | 0 |
| 8-30d | 0 |
| 31-90d | 1 |
| 91-365d | 0 |
| >365d | 0 |

Per-organization medians (n>=3):

- openai: 0d (n=5)

## Case study: which 'ChatGPT date' would you regress on?

- `announced`: 2022-11-30 (precision=day)
- `api_ga`: 2023-03-01 (precision=day)
- `consumer_rollout`: 2023-02-01 (precision=day)
- `free_tier`: 2022-11-30 (precision=day)

The candidate treatment dates for the same product span **91 days**. A difference-in-differences design with weekly or monthly bins can shift entire pre-periods into the post-period (and vice versa) purely by picking a different row of this table.

## Coverage

- models with an anchor event: 1125
- models with announced + an availability event: 186
