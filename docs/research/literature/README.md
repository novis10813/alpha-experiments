# Literature and Hypothesis Registry

This directory stores verified literature metadata and the narrow, testable
hypotheses extracted from it. It uses the existing lowercase `docs/research/`
hierarchy and does not replace factor notes or experiment reports.

## Contents

- [`registry.json`](registry.json) is the machine-readable index.
- [`papers/`](papers/) contains one note for each verified paper.
- [Literature note template](../templates/literature-note-template.md) is the note template.

## Schema

Each source entry contains:

- `paper_id`, normalized `canonical_source_id`, title, authors, year,
  `source_url`, `note_path`, `evidence_tier`, tags, identifiers, and status.
- `hypotheses`, each with a unique ID, source-grounded statement and mechanism,
  primary and context features from `EvolutionMarketState`, expected direction,
  positive diagnostic horizons, proposed classification, prerequisites, and
  missing fields.

The registry excludes validation or holdout results and result-derived fields such
as forward returns, thresholds, PnL, fills, positions, and drawdown. A hypothesis
is a proposed research input, not a claim that the repository has reproduced the
source.

## Validation and de-duplication

```bash
uv run python -m research.literature_registry --validate
uv run python -m research.literature_registry --check-source 10.1093/jjfinec/nbt003
uv run python -m research.literature_registry --check-source arxiv:2602.00776
```

Run `--check-source` before researching a candidate paper. DOI and arXiv forms are
normalized before lookup.

## Automated literature scout

The literature scout searches Semantic Scholar for relevant papers, uses an LLM
to evaluate relevance and extract structured hypotheses, and writes candidates
to [`staging.json`](staging.json) for human review.

```bash
# Run the full search → filter → extract → stage pipeline
uv run python -m research.literature_scout search

# Show what is currently staged
uv run python -m research.literature_scout status

# Approve a staged entry (moves it to registry.json and generates a note)
uv run python -m research.literature_scout approve <paper_id>
```

The scout requires `OPENROUTER_API_KEY` in the environment (same as evolution).
All staged entries have status `provisional` and evidence tier `primary_abstract`.
Approving an entry sets status to `verified`, validates the entry against the
full registry schema, and generates a literature note under `papers/`.
