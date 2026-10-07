# Repository Guide

The canonical map of this repository. Other documents link here instead of
restating these rules.

## Purpose and non-purpose

The repository builds observable market features and states, narrow alpha rows,
focused forward-return diagnostics, reports, and a bounded OpenEvolve search.

It does not turn every measured feature into a strategy, build or publish the
catalog, store credentials, commit generated outputs, or expose validation and
holdout evidence to exploratory work. Research conclusions are instrument- and
assumption-specific.

## Top-level map

| Directory | Responsibility |
| --- | --- |
| [`alphas/`](../alphas/) | Canonical alpha-producing functions and CLI entry points. Keep alpha rows narrow. |
| [`common/`](../common/) | Shared CSV, execution, kbar, resampling, and time-series helpers. |
| [`data/`](../data/) | Read-only Nautilus catalog access and market-data feature builders. See [`data/README.md`](../data/README.md). |
| [`evolution/`](../evolution/) | Discovery datasets, candidate evaluation, sandboxing, search families, promotion gates, and split governance. |
| [`experiments/`](../experiments/) | Runnable experiments and backtests, including the legacy SMA crossing command. |
| [`reports/`](../reports/) | Focused diagnostic and report builders. Generated files go under `outputs/`. |
| [`research/`](../research/) | Literature registry validator and automated literature scout. |
| [`tests/`](../tests/) | `unittest` coverage with local fixtures and mocks, no live catalog or service access. |
| [`docs/`](./) | Repository, alpha format, roadmap, and [research notes](research/README.md). |

## Configuration

- **Dependencies:** declare them in `pyproject.toml`, run `uv sync`, and keep
  `uv.lock` in step.
- **Catalog:** set `CATALOG_S3_ENDPOINT`, `CATALOG_S3_ACCESS_KEY`,
  `CATALOG_S3_SECRET_KEY`, and `CATALOG_OUTPUT_S3_BUCKET` in the shell or an
  untracked `.env`. See [`data/README.md`](../data/README.md).
- **Evolution:** `evolve` and `resume` use the self-hosted idlab vLLM endpoint
  and `qwen3.8-27b` from `evolution/configs/base.yaml`. Set `VLLM_API_KEY` outside
  the repository only if the endpoint requires it. `--iterations` is a total
  target, and `resume` defaults to the last approved target. New runs never
  overwrite existing run directories. Legacy runs without identity snapshots
  cannot resume safely.
- **Literature scout:** set `OPENROUTER_API_KEY`, and optionally `S2_API_KEY`,
  outside the repository.

Never copy secret values into code, docs, fixtures, logs, or examples.

## Local artifacts

| Path | Content | Ignored |
| --- | --- | --- |
| `outputs/` | Generated alpha exports, market extracts, reports, and diagnostics. Reproducible from commands in research notes. | yes, except `outputs/README.md` |
| `.local/` | Evolution datasets, governance ledgers, checkpoints, and build logs. | yes |
| `.pi/` | Agent workspace. | yes |
| `.worktrees/` | Agent worktrees. | no, only untracked |

Do not scan, summarize, or commit the contents of `.local/`, `.pi/`, or
`.worktrees/`. Before creating a new local artifact path, confirm it with
`git check-ignore`.

## Catalog policy

Use Nautilus Trader objects and APIs. `data/nautilus_catalog.py` builds a
read-only `ParquetDataCatalog` with path-style S3 settings. Do not replace it with
`ParquetDataCatalog.from_uri(...)` in this environment. Commands may read the
finished `nautilus-data` catalog but must not trigger conversion jobs, write to
S3, or require the homestack Docker network. The catalog builder is documented in
[`/opt/docker/docs/homestack/nautilus-catalog-builder.md`](/opt/docker/docs/homestack/nautilus-catalog-builder.md).

## Evolution boundaries

Discovery folds support repeated search and diagnosis. Validation selects from a
preregistered candidate set only after executable discovery qualification passes.
Holdout evaluates the validation champion once, under a family-level lock. Do not
use validation or holdout artifacts, results, or data to guide a hypothesis,
feature, fitness rule, or search configuration. Machine gates, not documentation
or operator intent, control access.

Details: [evolution guide](research/openevolve-strategy-evolution.md),
[promotion protocol](research/promotion-protocol.md), and
[experiment ledger](research/experiment-ledger.md).

## Commands

Run from the repository root:

```bash
uv sync
uv run python -m unittest discover -s tests
uv run python -m evolution --help
uv run python -m research.literature_registry --validate
```

The legacy SMA crossing backtest needs catalog settings and live catalog access.
It is not part of the offline test gate:

```bash
uv run python -m experiments.ma_crossing
```

Build the evolution sandbox image and point the runner at it:

```bash
docker build -f evolution/docker/Dockerfile -t alpha-evolution-sandbox:0.2 .
EVOLUTION_SANDBOX_IMAGE=alpha-evolution-sandbox:0.2 \
  uv run python -m evolution --help
```

The image build uses `uv sync --frozen --no-dev` and copies only the sandbox
runtime packages. A full evolution run also needs schema-v2 discovery data and
idlab vLLM access. Use `--dataset-root .local/evolution-data-v2` for the existing
v2 catalogs. Do not relabel v1 manifests to pass preflight.
