# Treatment-date sensitivity report

How far apart are the candidate 'release dates' of the same model?
Computed from the ledger's own dated events (global region, earliest
event per type, day/month precision as recorded). Gaps are in days;
positive means the second event happened after the first.

## announced -> api_ga

- median 0d (IQR 0-2d, n=134)
- range: 0d to 539d

| gap | models |
|---|---|
| same day | 88 |
| 1-7d | 16 |
| 8-30d | 6 |
| 31-90d | 10 |
| 91-365d | 13 |
| >365d | 1 |

Per-organization medians (n>=3):

- alibaba: 8d (n=8)
- google: 2d (n=18)
- xai: 0d (n=10)
- amazon: 0d (n=3)
- anthropic: 0d (n=19)
- deepseek: 0d (n=3)
- bytedance: 0d (n=10)
- zhipu: 0d (n=4)
- openai: 0d (n=35)
- meta: 0d (n=5)
- mistral: 0d (n=5)

## announced -> weights_released

- median 0d (IQR 0-1d, n=99)
- range: 0d to 870d

| gap | models |
|---|---|
| same day | 67 |
| 1-7d | 19 |
| 8-30d | 2 |
| 31-90d | 4 |
| 91-365d | 4 |
| >365d | 3 |

Per-organization medians (n>=3):

- baidu: 1d (n=3)
- alibaba: 0d (n=12)
- mistral: 0d (n=8)
- cohere: 0d (n=3)
- deepseek: 0d (n=9)
- google: 0d (n=10)
- zhipu: 0d (n=9)
- moonshot: 0d (n=5)
- meta: 0d (n=10)
- nvidia: 0d (n=7)
- minimax: 0d (n=5)

## announced -> consumer_rollout

- median 0d (IQR 0-9d, n=30)
- range: 0d to 117d

| gap | models |
|---|---|
| same day | 21 |
| 1-7d | 0 |
| 8-30d | 3 |
| 31-90d | 5 |
| 91-365d | 1 |
| >365d | 0 |

Per-organization medians (n>=3):

- anthropic: 0d (n=6)
- google: 0d (n=8)
- openai: 0d (n=14)

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

- models with an anchor event: 1840
- models with announced + an availability event: 223
