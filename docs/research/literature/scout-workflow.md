# Automated Literature Scout

The literature scout is a discovery aid for expanding the repository's initial
strategy hypotheses. It is deliberately separate from strategy evolution: it
finds and structures source-grounded ideas, but it does not create an evolution
family, alter a seed program, run a backtest, or promote an alpha.

## Scope and boundaries

The scout maps academic literature to the features exposed by
`evolution.market_state.EvolutionMarketState`. A paper's abstract and metadata
are evidence for a candidate research input, not evidence that the paper's
result transfers to the repository's Binance perpetual-futures data or that a
mapped idea is profitable.

The scout must not put forward-looking or evaluation-derived fields into a
literature entry. The registry validator rejects fields and keys associated with
validation, holdout, forward returns, PnL, drawdown, fills, positions,
thresholds, and z-scores. Keep those results in diagnostics or backtest outputs,
not in literature metadata.

## Pipeline

```text
LLM query generation
        ↓
Semantic Scholar search
        ↓
DOI/arXiv deduplication
        ↓
LLM relevance scoring
        ↓
LLM hypothesis extraction
        ↓
staging.json for human review
        ↓
explicit approval into registry.json
```

### 1. Query generation

The LLM receives the current `EvolutionMarketState` feature names and
high-level descriptions, plus existing source titles and hypothesis IDs. It
returns a list of academic search queries intended to cover diverse gaps rather
than repeat the current order-book-imbalance line.

This stage uses the same `OPENROUTER_API_KEY` as evolution and the default free
OpenRouter model configured in `research/llm_client.py`. Query generation has a
fallback query list if the response is not a JSON array.

### 2. Academic search

`research/academic_search.py` queries Semantic Scholar's paper search endpoint.
Each query requests title, abstract, authors, year, URL, DOI, and arXiv IDs. The
client skips results without an abstract, waits between unauthenticated
requests, and removes duplicate Semantic Scholar paper IDs across queries.

The client can use `S2_API_KEY` when available, but this is optional. A failed
search request does not expose credentials or write partial API responses to the
repository; it reports the failure and continues with available results.

### 3. Deduplication and relevance scoring

Papers are removed when their DOI or arXiv identifier already occurs in either
the durable registry or the staging file. Papers with neither identifier are
skipped because they cannot be safely de-duplicated or registered.

The LLM scores remaining papers from 0 to 10. Scores of 6 or higher proceed to
hypothesis extraction by default. The threshold and results-per-query are CLI
options; changing them changes the discovery breadth, not the registry's
promotion policy.

If a relevance response cannot be parsed, the current implementation keeps that
batch rather than silently discarding it. Reviewers should therefore treat the
staging gate as mandatory.

### 4. Hypothesis extraction

For each relevant paper, the LLM produces one source entry with one to three
hypotheses. The requested schema is the same as `registry.json`: normalized
source identity, evidence tier, status, feature mappings, expected direction,
diagnostic horizons, classification, prerequisites, and missing fields.

The implementation then overwrites identity-related values from the search
result where possible, sets `evidence_tier` to `primary_abstract`, sets
`status` to `provisional`, and removes feature names that are not in
`EvolutionMarketState.FIELDS`. It requires a DOI or arXiv ID. It does not verify
the paper's full text or claims on the user's behalf.

## Staging and approval

The staging path is `docs/research/literature/staging.json`. It is created on the
first successful extraction and has the same top-level source-list shape as the
durable registry. Repeated runs are idempotent for the same canonical source ID.

Use:

```bash
export OPENROUTER_API_KEY='<set outside the repository>'
uv run python -m research.literature_scout search
uv run python -m research.literature_scout status
uv run python -m research.literature_scout approve <paper_id>
```

`approve` is the human review gate. It changes the selected entry to
`verified`, generates a note under `docs/research/literature/papers/` when the
note does not exist, validates the combined registry, appends the entry to
`registry.json`, and removes it from staging. If validation fails, the registry
is not modified; fix the staging entry and retry.

Approval is not the same as research validation. After approval, the hypothesis
still needs a repository-specific factor note, timestamp-safe diagnostics, and
any appropriate executable or evolution checks. Validation and holdout evidence
must remain behind the evolution promotion gates.

## Operational cautions

- Run the scout from the repository root with `uv`.
- Keep `OPENROUTER_API_KEY` and any optional `S2_API_KEY` in the shell or an
  untracked local environment file; never write them into docs, staging data,
  logs, or prompts committed to the repository.
- Treat abstract-only entries as provisional research context even after the
  metadata is registered. Full-text verification should update the generated
  paper note before relying on a source-specific claim.
- Do not copy paper thresholds, costs, execution assumptions, validation results,
  or holdout results into the literature registry.
- Do not let the scout's relevance score become an evolution fitness score. The
  scout ranks literature relevance only; candidate strategies must use the
  trusted evolution evaluator and its promotion protocol.

## Verification

The offline checks for this workflow are:

```bash
uv run python -m research.literature_scout --help
uv run python -m research.literature_scout status
uv run python -m research.literature_registry --validate
git diff --check
```

The `search` command requires network access and `OPENROUTER_API_KEY`; it is not
part of the offline unit-test gate. The repository's tests should use mocked HTTP
responses rather than live Semantic Scholar or OpenRouter services.
