# Governance bundle: methods

Question: under what terms is each model offered, when was it
deprecated or withdrawn and what replaces it, and when did its developer
publish a system card or paper?

## Files

| File | What a row is |
|---|---|
| `models.csv` | one model with its license, `license_family` and the `license_has_usage_thresholds`, `license_requires_separate_agreement`, `license_has_branding_clause` and `license_has_use_restrictions` flags |
| `events.csv` | `license_changed`, `deprecation_announced`, `retired`, `system_card` and `paper_published` events; deprecations and retirements name `replacement_model_id` where the vendor names one |
| `claims.csv` | every source statement behind those events, including dates a source later moved (`superseded_on`) |
| `reschedules.csv` | each time a source moved its date for an event, with the signed number of days |
| `organizations.csv` | the developers `models.csv` names |

## How the rows are made

Retirements and deprecations come from vendor deprecation pages and
platform lifecycle tables (Azure Foundry, Amazon Bedrock, OpenRouter
expiry), corroborated by LiteLLM. A `retired` event with no `platform` is
the developer's shutdown; one with a platform is that host only. A
scheduled future date is kept as announced and re-read daily, and a move
is recorded as a superseded claim, so `reschedules.csv` is the history of
slipped shutdowns. System-card dates are from the developer's card index
at the precision it states (month for Anthropic's). `paper_published` is
the arXiv v1 submission day of the paper a person matched to the model.

## Limits

- `models.csv` holds today's terms; past terms appear only where a
  `license_changed` event records them.
- The `license_has_*` flags are a person's reading; blank is unread.
- System-card and paper coverage is partial. Google DeepMind's model-card
  index shows only "Updated" dates and is not used.
- Withdrawals without a retirement notice (a model silently dropped from
  a catalog) are in the Markets bundle's availability runs, not here.

Column definitions: `docs/schema.md`, sections "models.csv", "events.csv"
and "Generated artifacts". Data is CC BY 4.0 (see `LICENSE`).
