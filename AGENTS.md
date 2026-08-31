# AI Collaboration Entry Point

Read this root `AGENTS.md` first. When work targets a subdirectory, read the
nearest `AGENTS.md` in that path as well. If instructions conflict, the
`AGENTS.md` closer to the target file has higher priority. Each layer indexes
only its own direct child instructions; follow the nearer file rather than
scanning the whole tree.

## Repository Scope

This repository contains local, hypothesis-based alpha research built on Nautilus
Trader. It produces narrow alpha rows, diagnostics, reports, and bounded
OpenEvolve research experiments. The [repository guide](docs/repository-guide.md)
is the canonical map and records the project's non-purpose, directory roles, data
boundaries, and operating commands.

## Configuration and File Placement

- Read [the repository guide](docs/repository-guide.md) for the overall layout and
  local-artifact boundaries.
- Read [`data/README.md`](data/README.md) before catalog-backed work. Put catalog
  connection settings in the shell or an untracked `.env`; keep catalog reads
  read-only and use Nautilus data objects.
- Read [`docs/alpha-signal-format.md`](docs/alpha-signal-format.md) before adding
  alpha output. Put canonical alpha logic in `alphas/`; keep diagnostics and
  derived measures in `reports/` or research notes.
- Read [`docs/research/current-focus.md`](docs/research/current-focus.md) and the
  [research framework](docs/research/research-framework.md) before new factor
  work. Put durable findings under `docs/research/`; put generated artifacts
  under `outputs/`.
- For literature discovery, read
  [`docs/research/literature/scout-workflow.md`](docs/research/literature/scout-workflow.md).
  Scout results are provisional until human approval and are not strategy
  evidence.
- Read the [evolution guide](docs/research/openevolve-strategy-evolution.md) and
  [promotion protocol](docs/research/promotion-protocol.md) before evolution
  work. Keep datasets, checkpoints, governance ledgers, and runtime material in
  local paths such as `.local/` and `outputs/`; verify ignore coverage before
  creating a new artifact path.
- Keep dependency declarations in `pyproject.toml` and the lockfile in `uv.lock`.
  Keep Docker sandbox instructions and implementation under `evolution/docker/`.

## Instruction Index

### Existing child instructions

- [`research/AGENTS.md`](research/AGENTS.md) — local rules for the literature registry and automated literature scout.

Do not infer child policy from generated or runtime directories.

### Candidate future locations

If one of these directories becomes complex enough to need local rules, add an
`AGENTS.md` there and update this nearest-ancestor index:

- `evolution/`
- `reports/`
- `data/`
- `docs/research/`

Apply the same rule to any other directory whose local workflow needs instructions.
When a directory becomes complex enough to need an `AGENTS.md`, add it there and
update the **nearest ancestor** `AGENTS.md` index. Do not make a parent index
enumerate the entire subtree.

## Working Rules

- Prefer Nautilus Trader APIs and objects over ad hoc market-data structures.
- Make small, focused changes. Do not perform opportunistic refactors.
- Preserve unrelated dirty changes; never overwrite work you did not make.
- Keep secrets, generated outputs, runtime directories, and local credentials out
  of tracked files.
- Do not access validation or holdout data before the machine-enforced promotion
  gates allow it. Do not use validation or holdout results to guide discovery.
- Preserve timestamp semantics: completed aggregation states become knowable at
  the interval end, with no lookahead.
- Keep the canonical alpha row narrow. Put prices, forward returns, costs,
  thresholds, positions, fills, PnL, and drawdown in diagnostics or backtests.

## Verification

Use `uv` for Python commands. Run the checks relevant to the change, including:

```bash
uv sync
uv run python -m unittest discover -s tests
uv run python -m evolution --help
uv run python -m research.literature_registry --validate
git diff --check
```

For catalog-backed legacy work, `uv run python -m experiments.ma_crossing` requires
catalog environment variables and live catalog access. Do not treat it as an
offline unit-test check. Confirm that only requested documentation files changed
before reporting completion.

## Maintenance

Keep this file concise. Link to detailed policy instead of copying it. When a
child directory becomes complex, create its `AGENTS.md`, add it to the index above,
and update the nearest ancestor instructions.
