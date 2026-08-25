# Changelog

All notable changes to the llm-ledger dataset and pipeline are recorded here.
Data corrections update rows in place; this file preserves the history.

## 2026-08-25

- Initial repository scaffold: schema, validation rules, empty core tables.
- First ingestion: catalog pullers (models.dev, OpenRouter, Epoch AI, arXiv,
  keyed vendor APIs), cross-source matcher (493 models matched across >=2
  sources), reconciler loading 337 models / 433 inferred events, and the
  cross-source disagreement report.
- Primary-source verification for 56 core models (vendor blogs, deprecation
  pages, arXiv, HF Hub timestamps); 85.9% of in-scope availability events
  verified; cross-source date conflicts stored as disputed with all values
  in notes (Kimi K3 weights date, Mixtral aggregator claim). Attributes
  table populated for 50 models.
- Hugging Face open-weight sweep (2013 repos, inclusion rule applied,
  per-org download cap) adding ~730 models and ~830 `weights_released`
  events dated by repo `createdAt`; Chinese-lab share of open-weight rows
  50%. NHLOCAL AiTimeline (CC BY) discovery leads queued for review, never
  loaded into core.
- Vendor-changelog pass: 16 verified `price_changed` / `feature_added` /
  `alias_repointed` events for core models (Anthropic release notes, Mistral
  changelog, archived OpenAI announcements); one verified event dropped for
  a vocabulary gap and queued for review.
- Treatment-date sensitivity report from the ledger's own dates.
- Derived fields and wide/enriched artifacts rebuild byte-identically
  (validation rule 9); full-pipeline rerun confirmed idempotent.
- Deduplication audit: merged nine duplicate model rows caused by two
  identity-rule splits (vendor "qwen2-5" vs aggregator "qwen-2-5" spelling;
  short keys org-prefixed by reconcile but not the census). Matcher now
  bridges letter-digit boundary spellings, reconcile pins clusters to
  already-crosswalked identifiers, and both scripts share one slug rule.
  Filled availability gaps: GPT-4.5 consumer/API preview events from the
  archived launch post; three announced-only open-weight models dated from
  their HF repo timestamps.
