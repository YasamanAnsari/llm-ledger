# Treatment-date sensitivity report

How far apart are the candidate 'release dates' of the same model?
Computed from the ledger's own dated events (global region, earliest
event per type, day/month precision as recorded). Gaps are in days;
positive means the second event happened after the first.

## announced -> api_ga

- median 0d (IQR 0-2d, n=131)
- range: 0d to 701d

| gap | models |
|---|---|
| same day | 82 |
| 1-7d | 19 |
| 8-30d | 6 |
| 31-90d | 9 |
| 91-365d | 12 |
| >365d | 3 |

Per-organization medians (n>=3):

- google: 2d (n=19)
- alibaba: 2d (n=9)
- amazon: 0d (n=3)
- anthropic: 0d (n=18)
- mistral: 0d (n=7)
- microsoft: 0d (n=5)
- deepseek: 0d (n=3)
- bytedance: 0d (n=4)
- zhipu: 0d (n=4)
- openai: 0d (n=34)
- xai: 0d (n=9)
- meta: 0d (n=3)

## announced -> weights_released

- median 0d (IQR 0-1d, n=68)
- range: 0d to 770d

| gap | models |
|---|---|
| same day | 45 |
| 1-7d | 15 |
| 8-30d | 4 |
| 31-90d | 1 |
| 91-365d | 2 |
| >365d | 1 |

Per-organization medians (n>=3):

- nvidia: 6d (n=6)
- alibaba: 1d (n=8)
- mistral: 0d (n=6)
- cohere: 0d (n=3)
- deepseek: 0d (n=7)
- meta: 0d (n=9)
- google: 0d (n=7)
- zhipu: 0d (n=5)
- moonshot: 0d (n=4)
- minimax: 0d (n=3)

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

- models with an anchor event: 1168
- models with announced + an availability event: 191
