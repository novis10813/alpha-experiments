# Repository Guide

This guide is the canonical map for contributors and coding agents. Read it
before changing research code or operating a data-backed experiment.

## Purpose and non-purpose

This repository contains local alpha research built on Nautilus Trader. It
supports observable market features and states, narrow alpha rows, focused
forward-return diagnostics, report generation, and a bounded OpenEvolve search
workflow.

The repository does not turn every measured feature into a strategy. It does not
build or publish the homestack catalog, store credentials, commit generated
outputs, or expose validation and holdout evidence for exploratory iteration.
Read the finished catalog only. Treat research conclusions as instrument- and
assumption-specific.

## Top-level map

| Directory | Responsibility |
| --- | --- |
| [`alphas/`](../alphas/) | Canonical alpha-producing functions and CLI entry points. Keep alpha rows narrow. |
| [`common/`](../common/) | Shared CSV, execution, kbar, resampling, and time-series helpers. |
| [`data/`](../data/) | Read-only Nautilus catalog access and market-data feature builders. See [`data/README.md`](../data/README.md). |
| [`evolution/`](../evolution/) | Discovery datasets, candidate evaluation, sandboxing, search families, promotion gates, and split governance. |
| [`experiments/`](../experiments/) | Runnable experiments and backtests, including the legacy SMA crossing command. |
| [`reports/`](../reports/) | Focused diagnostic and report builders. Generated report files belong under `outputs/`. |
| [`research/`](../research/) | Small research-support modules, including the literature registry validator and automated literature scout. Durable research decisions belong under [`docs/research/`](research/). |
| [`tests/`](../tests/) | `unittest` coverage. Tests should use local fixtures and mocks rather than live catalog or service access. |
| [`docs/`](./) | Durable repository, alpha, research, roadmap, literature, and evolution documentation. |

The root also contains `pyproject.toml` and `uv.lock` for the environment, and
`main.py` for the repository's small top-level entry point. `outputs/` is a
local scratch area; its generated contents are not part of the repository map.

## Configuration, secrets, and generated material

- **Dependencies:** edit `pyproject.toml` only when a dependency change is
  needed, then run `uv sync`; keep the lockfile in step with the project.
- **Catalog runtime configuration:** set `CATALOG_S3_ENDPOINT`,
  `CATALOG_S3_ACCESS_KEY`, `CATALOG_S3_SECRET_KEY`, and
  `CATALOG_OUTPUT_S3_BUCKET` in the shell or an untracked local `.env`. Follow
  [`data/README.md`](../data/README.md) and the operational catalog guide; do
  not copy secret values into code, docs, fixtures, logs, or examples.
- **Evolution and literature-scout runtime configuration:** provide
  `OPENROUTER_API_KEY` outside the repository when running `evolution evolve`,
  `resume`, or `research.literature_scout`. The optional `S2_API_KEY` can reduce
  Semantic Scholar rate limiting. Evolution datasets, governance ledgers,
  checkpoints, and run scratch data belong under `.local/` or `outputs/`, not in
  tracked documentation.
- **Generated outputs:** write alpha exports, market extracts, reports, and
  evolution summaries under `outputs/`; keep them reproducible from commands in
  durable research notes. `.local/`, `.pi/`, and `.worktrees/` are runtime or
  agent-workspace directories. Do not scan, summarize, or commit their contents.
  Before creating a new local artifact path, confirm its ignore status with
  `git check-ignore`; the current ignore rules cover `outputs/*` and
  `.local/evolution-data*`, while other local directories may remain merely
  untracked.

## Catalog policy

Use Nautilus Trader objects and APIs. `data/nautilus_catalog.py` constructs a
read-only `ParquetDataCatalog` with the environment's path-style S3 settings.
Do not replace it with `ParquetDataCatalog.from_uri(...)` in this environment.
Repository commands may read the finished `nautilus-data` catalog, but must not
trigger conversion jobs, write to S3, or require the homestack Docker network.
The catalog builder's operational documentation is
[`/opt/docker/docs/homestack/nautilus-catalog-builder.md`](/opt/docker/docs/homestack/nautilus-catalog-builder.md).
See [`data/README.md`](../data/README.md) for connection details and examples.

## Research entry points

Start a research session with [`docs/research/current-focus.md`](research/current-focus.md),
then use [`docs/research/research-framework.md`](research/research-framework.md)
and the [factor template](research/templates/factor-research-template.md). The
[research index](research/README.md) summarizes current factor notes and the
[literature registry](research/literature/README.md) records verified sources and
source-grounded hypotheses. The [literature scout workflow](research/literature/scout-workflow.md)
describes automated paper discovery and its staging/approval boundary. Keep the
canonical alpha row defined by
[`docs/alpha-signal-format.md`](alpha-signal-format.md); keep forward returns,
costs, thresholds, positions, fills, PnL, and drawdown in diagnostics or
backtests.

## Evolution boundaries

Evolution uses chronological discovery folds for repeated search and diagnosis.
Validation selects from a preregistered candidate set only after the executable
discovery qualification gates pass. Holdout evaluates the validation champion
once, under a family-level lock. Do not inspect validation or holdout artifacts,
results, or generated data to guide a hypothesis, feature, fitness rule, or
search configuration. Machine gates, not documentation or operator intent,
control access.

Use the detailed [evolution strategy guide](research/openevolve-strategy-evolution.md)
for the current workflow and the [promotion protocol](research/promotion-protocol.md)
for qualification, validation, holdout, and research statuses. The [experiment
ledger](research/experiment-ledger.md) explains family identity and local
holdout locks. The [execution parity](research/execution-parity.md), [eligibility
audit](research/eligibility-gate-audit.md), and [cost and delay sensitivity](research/cost-delay-sensitivity.md)
docs cover discovery diagnostics without repeating their policies here.

## Verified commands

Run these from the repository root:

```bash
uv sync
uv run python -m unittest discover -s tests
uv run python -m evolution --help
uv run python -m research.literature_registry --validate
```

The legacy SMA crossing backtest remains available:

```bash
uv run python -m experiments.ma_crossing
```

It requires catalog environment variables and live access to the finished catalog;
it is not part of the offline unit-test gate.

Build the current sandbox image with the repository's 0.2 tag, then use it for
an evolution run:

```bash
docker build -f evolution/docker/Dockerfile -t alpha-evolution-sandbox:0.2 .
EVOLUTION_SANDBOX_IMAGE=alpha-evolution-sandbox:0.2 \
  uv run python -m evolution --help
```

The image build uses `uv sync --frozen --no-dev` and copies only the runtime
packages needed by the sandbox. A full evolution run additionally needs prepared
local discovery data and `OPENROUTER_API_KEY`; follow the detailed evolution
documentation before running it.
