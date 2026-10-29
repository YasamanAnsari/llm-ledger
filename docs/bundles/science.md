# Science bundle: methods

Question: which models does research use, how soon after release, which
exact version was served, and how capable was it?

## Files

| File | What a row is |
|---|---|
| `research_mentions.csv` | one arXiv paper version (cs.AI, cs.CL, cs.CV, cs.LG, stat.ML) and one model or family its title or abstract names |
| `research_mentions_monthly.csv` | papers per family per month |
| `research_first_mentions.csv` | each model a paper names, with the first such paper and `days_to_first_mention` from first public availability |
| `citation_observations.csv` | one model's arXiv paper and its citation count from OpenAlex (total and by citing year) or Semantic Scholar (total) |
| `model_versions.csv` | a run of days on which a source stated one version of an id: a Hub commit sha or a dated API snapshot |
| `llm_ledger_capability.csv` | an Epoch Capabilities Index score joined to a ledger model |
| `llm_ledger_benchmarks.csv` | one Epoch Benchmarking Hub result (benchmark, evaluated version, score) on a ledger model |
| `llm_ledger_arena.csv` | one LMArena rating of a ledger model on one arena's published leaderboard |
| `events.csv` | `paper_published`, `weights_released` and `version_observed` events |
| `claims.csv` | every source statement behind those events |
| `models.csv`, `organizations.csv` | the identifiers every other file uses |

## How the rows are made

Mentions come from arXiv's OAI-PMH feed. Titles and abstracts are split
into letter and number runs and compared, longest first, with the
ledger's own spellings: model names, Epoch, Hub and vendor API ids for
model mentions, family names and `text_surface_forms` spellings for
family mentions. The match is deterministic; no model reads the text.
Versions are copied from the Hub and vendor model APIs on each daily
pull. ECI scores are joined by Epoch's own model name through
`crosswalk.csv`, or by a normalized name when the crosswalk holds none.
Epoch benchmark results join the same way through each version's model
group. Arena names join when, with an effort qualifier folded, they are a
ledger id or a unique ledger spelling; a dated name needs a ledger id
with the same date or an arena that lists the model under one date only.
A model's paper is the arXiv link of its `paper_published` event, else
the one Epoch AI gives, else the single `arxiv:` tag on its Hub repos;
OpenAlex and Semantic Scholar are asked for that paper by arXiv id.

## Limits

- Citation counts are copied from each source and disagree (OpenAlex
  counts an arXiv preprint apart from its journal version, so it runs
  lower). A Hub tag can name a method or base-model paper, so a
  fine-tune may carry its base model's count. Models with no arXiv paper
  have no row.

- Mentions are a floor. A spelling needs a version or size digit, so bare
  names ("Qwen", "Claude", "Phi") are not counted, and only titles and
  abstracts are read, not full text. Punctuation inside a spelling breaks
  it, and a word, a space and a bare number must be capitalized ("Llama
  3", not "step 3"); capitalized prose ("Step 3") can still match.
- A mention is dated by the version whose text was read, the latest at
  harvest; an earlier version may not have named the model.
- Papers submitted before the harvest start (`harvested_from` in
  `data/staging/research_harvest.json`) and not revised since were not
  read; `days_to_first_mention` is blank for models available before it.
- Monthly counts are not normalized by arXiv's growing volume.
- A new Hub sha may change only the model card.
- ECI has no index version or per-model evaluation date;
  `eci_snapshot_date` is the day the scores file was archived. Compare
  scores within one snapshot.
- Arena ratings are refit at each publication; compare models within one
  leaderboard. Models the ledger does not hold, and names it cannot place
  on one model, are not in the join.
- Epoch benchmarks without a declared score column, and Epoch rows
  sourced from Artificial Analysis, are not included.

Column definitions: `docs/schema.md`. arXiv metadata is CC0 1.0; ECI and
the Benchmarking Hub are CC BY 4.0 (Epoch AI); LMArena's leaderboard
dataset is CC BY 4.0 (LMArena); OpenAlex is CC0; citation counts from
Semantic Scholar are credited "Semantic Scholar"; the ledger is CC BY 4.0
(see `LICENSE`).
