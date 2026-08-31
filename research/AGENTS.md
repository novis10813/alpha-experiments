# Research Collaboration Instructions

This file is the AI collaboration entry point for `research/`. Read the root
[`AGENTS.md`](../AGENTS.md) first; when instructions conflict, the file nearest
the target has priority. Detailed research policy lives in
[`docs/research/research-framework.md`](../docs/research/research-framework.md)
and the repository map in [`docs/repository-guide.md`](../docs/repository-guide.md).

## Scope

`research/` contains small research-support modules, not canonical alpha logic,
reports, or evolution strategy families. Current modules include the literature
registry validator and the automated literature scout.

## Local architecture

- `literature_registry.py` validates and queries the durable JSON registry at
  `docs/research/literature/registry.json`.
- `literature_scout.py` searches papers, asks the configured LLM to score and
  structure hypotheses, and stages candidates at
  `docs/research/literature/staging.json`.
- `academic_search.py` is the Semantic Scholar HTTP client used by the scout.
- `llm_client.py` is the stdlib-only OpenRouter HTTP client shared by the scout.

The scout's workflow, source boundary, staging gate, and operational cautions are
defined in [`docs/research/literature/scout-workflow.md`](../docs/research/literature/scout-workflow.md).
Do not turn scout output directly into a strategy or claim; approval only adds
source metadata and proposed hypotheses to the registry.

## Local conventions

- Keep HTTP clients dependency-free unless a dependency change is explicitly
  required; use `uv` and declare any necessary dependency in the root
  `pyproject.toml` and `uv.lock`.
- Keep credentials in environment variables. The scout reads
  `OPENROUTER_API_KEY`; optional `S2_API_KEY` is also external configuration.
- Preserve registry normalization and validation by reusing
  `research.literature_registry` helpers rather than creating a second schema.
- Treat `staging.json` as a review queue. Do not silently merge staging entries
  into the durable registry or write model results into registry fields.
- Use mocked HTTP responses in tests; do not make live Semantic Scholar or
  OpenRouter calls in the offline test suite.

## Verification

From the repository root:

```bash
uv run python -m research.literature_scout --help
uv run python -m research.literature_scout status
uv run python -m research.literature_registry --validate
```

Run the full unit-test suite and `git diff --check` when changing shared behavior.

## Instruction Index

### Existing child instructions

None.

### Maintenance

If a direct child directory becomes complex enough to need its own
`AGENTS.md`, add it there and update this index. Do not enumerate deeper
instructions here; each directory owns its direct-child index.
