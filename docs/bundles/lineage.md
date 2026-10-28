# Lineage bundle: methods

Question: what was each model built from, what was built from it, how
open is it, and how have its terms changed?

## Files

| File | What a row is |
|---|---|
| `models.csv` | one model, with its lineage links (`base_model_id`, `parent_model_id`, `snapshot_of`, `predecessor_id`, `successor_id`), derivative type, openness (`access_type`, `training_data_released`, `training_code_released`) and license columns |
| `crosswalk.csv` | the model's ids in other catalogs (Hub repos, vendor APIs, Epoch, OpenRouter) |
| `events.csv` | `announced`, `weights_released`, `license_changed`, `renamed` and `alias_repointed` events |
| `claims.csv` | every source statement behind those events |
| `organizations.csv` | the developers `models.csv` names |

## How the rows are made

`base_model_id` and `derivative_type` come from a person, or on
machine-drafted rows from the Hub repo's `base_model:` tags, only when
every tagged base resolves to one ledger model and the link closes no
cycle. Quantizations, adapters and community merges are out of scope
unless famous on their own. `predecessor_id` and `successor_id` are set
by a person; `build.py` queues family version order as review leads, not
links. Licenses are the repo's license tag or the vendor's stated terms,
grouped into `license_family`; the `license_has_*` flags are a person's
reading of the license text, blank where unread. A `license_changed`
event carries `old->new` and the day the new terms applied.

## Limits

- Lineage links are sparse: most open-weight models name no base model,
  and many families have no predecessor links yet.
- `models.csv` holds today's license; earlier terms are only where a
  `license_changed` event records them, so license history is incomplete.
- `training_data_released` and `training_code_released` are filled for
  the fully open models reviewed so far and blank elsewhere; blank means
  unknown, not false.
- Open-weight models with no `license_family` are counted in
  `data/generated/coverage_report.md`.

Column definitions: `docs/schema.md`, sections "models.csv" and
"events.csv". Data is CC BY 4.0 (see `LICENSE`).
