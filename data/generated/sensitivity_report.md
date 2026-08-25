# Treatment-date sensitivity report

How far apart are the candidate 'release dates' of the same model?
Computed from the ledger's own dated events (global region, earliest
event per type, day/month precision as recorded). Gaps are in days;
positive means the second event happened after the first.

## announced -> api_ga

- median 0d (IQR 0-2d, n=204)
- range: 0d to 770d

| gap | models |
|---|---|
| same day | 126 |
| 1-7d | 38 |
| 8-30d | 11 |
| 31-90d | 13 |
| 91-365d | 12 |
| >365d | 4 |

Per-organization medians (n>=3):

- perplexity: 34d (n=3)
- alibaba: 2d (n=17)
- baidu: 1d (n=4)
- google: 1d (n=24)
- amazon: 0d (n=3)
- anthropic: 0d (n=20)
- mistral: 0d (n=14)
- microsoft: 0d (n=5)
- cohere: 0d (n=4)
- deepseek: 0d (n=9)
- bytedance: 0d (n=4)
- meta: 0d (n=12)
- zhipu: 0d (n=9)
- openai: 0d (n=37)
- xai: 0d (n=9)
- moonshot: 0d (n=5)
- nvidia: 0d (n=7)
- xiaomi: 0d (n=3)
- minimax: 0d (n=6)

## announced -> weights_released

- median -1d (IQR -6-0d, n=65)
- range: -24d to 22d

| gap | models |
|---|---|
| same day | 13 |
| 1-7d | 36 |
| 8-30d | 16 |
| 31-90d | 0 |
| 91-365d | 0 |
| >365d | 0 |

Per-organization medians (n>=3):

- deepseek: 0d (n=8)
- zhipu: -1d (n=7)
- moonshot: -1d (n=5)
- minimax: -1d (n=6)
- alibaba: -2d (n=8)
- meta: -4d (n=9)
- google: -11d (n=7)

## announced -> consumer_rollout

- median 0d (IQR 0-30d, n=22)
- range: 0d to 117d

| gap | models |
|---|---|
| same day | 14 |
| 1-7d | 0 |
| 8-30d | 2 |
| 31-90d | 5 |
| 91-365d | 1 |
| >365d | 0 |

Per-organization medians (n>=3):

- openai: 15d (n=12)
- anthropic: 0d (n=6)

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

- models with an anchor event: 1149
- models with announced + an availability event: 217
