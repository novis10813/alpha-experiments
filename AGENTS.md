# AGENTS.md

The repo holds shared market-data and evolution infrastructure and one report per research
task. These rules keep `main` clean while experiments stay reproducible.

## Branches

| Branch | Purpose | Rules |
|---|---|---|
| `task/T<NN>-<name>` | one per task; experiments and trial and error | Anything goes, but never rebase, force-push or delete it (a GitHub ruleset blocks both) |
| `clean/T<NN>-<name>` | branched from `task/T<NN>-<name>` when the task ends; holds only what passes the file rule | Opened as a PR to `task/T<NN>-<name>`. Deleted once that PR is merged |
| `chore/<name>` | changes outside any task: refactors, documentation, tooling, these rules | Short-lived. Opened as a PR to `main` and deleted once merged. A refactor must not change research or evolution results |
| `main` | runnable code and every finished task | Every new task branches from it. Receives a task only by merging its `task/` branch after the `clean/` PR |

Task numbers are two digits and never reused: `T01`, `T02`, ...

Tasks run one at a time: `task/T<NN+1>` branches from `main` after `T<NN>` is merged, so it
starts with everything earlier tasks changed.

## Workflow per task

1. Branch `task/T<NN>-<name>` from `main`. Commit before every run whose results may go into
   the report, so each run maps to a commit.
2. For every run whose results go into the report:
   - write its outputs to `outputs/T<NN>-<name>/<run id>/`. An evolution run ID is its
     `--run-id`;
   - tag the commit it ran with an annotated tag `exp/T<NN>-<run id>`. The tag message
     records what the report leaves out: the command, instruments, data window or splits,
     seed, dataset manifest hashes, and the repo-relative output paths. No host names or
     credentials: the repo is public.

   A tag never points to a different commit. Its message may be corrected by re-creating
   the tag on the same commit.
3. Branch `clean/T<NN>-<name>` from `task/T<NN>-<name>`. Move, rewrite or delete files until
   only what passes the file rule is left, and open a PR to `task/T<NN>-<name>`.
4. After that PR is merged, open a PR from `task/T<NN>-<name>` to `main`.
5. After the merge, create a GitHub release `T<NN>-<name>` on the merge commit. Its notes
   summarize the results, and its assets are the result tables behind every reported
   number.
6. Keep the `task/` branch and its tags after the merge. Files deleted in step 3 stay
   reachable through them.

## File rule

A file goes to `main` only if it is needed to:

- **run** an alpha, feature builder, evolution search or diagnostic: library code, entry
  points, environment setup;
- **reproduce** a reported number or figure: configs, analysis scripts;
- **understand** the repo: `README.md`, this file, protocols, task READMEs.

Everything else (debugging, abandoned attempts, superseded scripts and figures) is deleted on
the `clean/` branch. It stays in the `task/` branch's history and tags.

## Layout

```
alphas/ common/ evolution/ research/     shared code: alphas, catalog and market-data helpers, evolution runtime, literature tools
evolution/docs/                          evolution protocols: strategy evolution guide, promotion, ledger, cost profiles
evolution/families/<id>/                 family preregistration (README.md) and initial program
scripts/                                 shared entry points (run as `python -m scripts.<name>`)
analysis/                                analysis tools used by two or more tasks
docs/                                    research framework, current focus, roadmap, alpha format, literature
tasks/README.md                          task index: status and report per task
tasks/T<NN>-<name>/
  REPORT.md                              results only
  README.md                              how to reproduce: commands, configs, code changes
  configs/                               experiment configs (search configs, seeds)
  figures/                               figures used in REPORT.md
  *.py                                   analysis used only by this task (run as `python -m tasks.T<NN>-<name>.<module>`)
tests/                                   offline unittest suite
data/                                    git-ignored: datasets, manifests, governance ledgers
outputs/                                 git-ignored: generated outputs and logs
```

- A change to shared code that can alter research or evolution results goes behind a new
  argument or config key whose default keeps the original behaviour, so every earlier result
  still reproduces from `main`. Changes that only affect logging or which files are kept need
  no switch.
- A task's analysis script moves to `analysis/` only when a second task needs it. The same PR
  updates the commands in earlier tasks' READMEs.
- Task modules import siblings relatively (`from .module import ...`), because the task
  directory name is not a valid identifier.

## Reports

- `REPORT.md` presents results: setup, numbers, figures, comparisons, limitations, status.
- No local paths, hashes, host names or logs in reports. Those go in the `exp/` tag messages.
- Every number and figure in a report must be regenerable with a command in the task's
  `README.md`, from the catalog or the task's release assets.
  Numbers quoted from other sources (papers, other repos) name their source instead.
- Record rejected and inconclusive results. When a bug or data issue changes a result, state
  the correction explicitly.

## Research rules

- Prefer Nautilus Trader APIs and objects over ad hoc market-data structures.
- Do not access validation or holdout data before the promotion gates allow it, and never use
  their results to guide discovery.
- Completed aggregation states become knowable at the interval end. No lookahead.
- Keep the canonical alpha row narrow. Prices, returns, costs, positions, fills, and PnL
  belong in diagnostics or backtests. See [`docs/alpha-signal-format.md`](docs/alpha-signal-format.md).
- Literature scout output is staging only, not strategy evidence. See
  [`research/AGENTS.md`](research/AGENTS.md).

## Data and outputs

Datasets, manifests, ledgers, outputs and logs are never committed.

- `data/` holds evolution datasets with their manifests (`data/evolution-data*`) and the
  governance ledgers (`data/evolution-governance/`). Ledgers record validation and holdout
  use and cannot be regenerated: never delete them.
- `outputs/` holds everything regenerable: alpha exports, market extracts, reports,
  diagnostics, evolution runs and logs (`outputs/logs/`).
- Results that must outlive this machine go in `exp/` tag messages and release assets.
- The market data source is the read-only homestack `nautilus-data` Parquet catalog
  (`BNBUSDT`, `BTCUSDT`, `ETHUSDT` on `BINANCE`, `trade_tick` and `order_book_depths`).
  Set `CATALOG_S3_ENDPOINT`, `CATALOG_S3_ACCESS_KEY`, `CATALOG_S3_SECRET_KEY` and
  `CATALOG_OUTPUT_S3_BUCKET` in the shell or an untracked `.env`, using a read-only
  credential. `common/nautilus_catalog.py` builds the catalog with path-style S3 settings.
  Do not replace it with `ParquetDataCatalog.from_uri(...)`. Builder documentation:
  [`/opt/docker/docs/homestack/nautilus-catalog-builder.md`](/opt/docker/docs/homestack/nautilus-catalog-builder.md).

## Verification

Use `uv` for Python commands. Run the checks relevant to the change:

```bash
uv sync
uv run python -m unittest discover -s tests
uv run python -m evolution --help
uv run python -m research.literature_registry --validate
git diff --check
```

Before reporting completion, confirm that only intended files changed.

## Instruction index

- [`research/AGENTS.md`](research/AGENTS.md): literature registry and scout.
- [`evolution/AGENTS.md`](evolution/AGENTS.md): evolution runtime, families, protocols, and boundaries.

When a directory needs its own rules, add an `AGENTS.md` there and list it here.

## Tasks

T01 to T08 predate these rules. They have no `task/` branch, `exp/` tags or release, and
their notes were split into `REPORT.md` and `README.md` during the migration. Status and
report per task: [`tasks/README.md`](tasks/README.md).

Current research state and next work: [`docs/research/current-focus.md`](docs/research/current-focus.md).

---

# Repository guide

Rules above win on conflict.

## Purpose and non-purpose

The repository builds observable market features and states, narrow alpha rows,
focused forward-return diagnostics, reports, and a bounded OpenEvolve search.

It does not turn every measured feature into a strategy, build or publish the
catalog, store credentials, commit generated outputs, or expose validation and
holdout evidence to exploratory work. Research conclusions are instrument- and
assumption-specific.

## Configuration

- **Dependencies:** declare them in `pyproject.toml`, run `uv sync`, and keep
  `uv.lock` in step.
- **Catalog:** see [Data and outputs](#data-and-outputs).
- **Literature scout:** set `OPENROUTER_API_KEY`, and optionally `S2_API_KEY`,
  outside the repository.

Never copy secret values into code, docs, fixtures, logs, or examples.

## Local artifacts

| Path | Content | Ignored |
| --- | --- | --- |
| `data/` | Evolution datasets, manifests, and governance ledgers. | yes |
| `outputs/` | Generated alpha exports, market extracts, reports, diagnostics, evolution runs, and logs. | yes, except `outputs/README.md` |
| `.pi/` | Agent workspace. | yes |
| `.worktrees/` | Agent worktrees. | no, only untracked |

Do not scan, summarize, or commit the contents of `data/`, `.pi/`, or
`.worktrees/`. Before creating a new local artifact path, confirm it with
`git check-ignore`.

## Catalog policy

Commands may read the finished `nautilus-data` catalog but must not trigger
conversion jobs, write to S3, or require the homestack Docker network. MinIO needs
path-style requests: the helper keeps `addressing_style=path` and
`virtual_hosted_style_request=false`, and the `fs_rust_storage_options` endpoint
key must be `endpoint_url`.
