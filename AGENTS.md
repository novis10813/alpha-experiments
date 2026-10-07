# AI Collaboration Entry Point

Read this file first. When work targets a subdirectory, also read the nearest
`AGENTS.md` in that path. The file closer to the target wins on conflict.

The [repository guide](docs/repository-guide.md) is the canonical map: directory
roles, data boundaries, local artifacts, and commands.

## Read before you start

| Work | Read first | Put results in |
| --- | --- | --- |
| Catalog-backed data | [`data/README.md`](data/README.md) | `outputs/` |
| Alpha output | [`docs/alpha-signal-format.md`](docs/alpha-signal-format.md) | `alphas/` for canonical logic, `reports/` for diagnostics |
| New factor or hypothesis | [Current focus](docs/research/current-focus.md), [research framework](docs/research/research-framework.md) | `docs/research/` for findings, `outputs/` for artifacts |
| Literature discovery | [Scout workflow](docs/research/literature/scout-workflow.md) | Staging only; scout output is not strategy evidence |
| Evolution | [Evolution guide](docs/research/openevolve-strategy-evolution.md), [promotion protocol](docs/research/promotion-protocol.md) | `.local/` and `outputs/` |

## Instruction index

- [`research/AGENTS.md`](research/AGENTS.md): literature registry and scout.

When a directory needs its own rules, add an `AGENTS.md` there and list it in the
nearest ancestor's index only.

## Working rules

- Prefer Nautilus Trader APIs and objects over ad hoc market-data structures.
- Make small, focused changes. No opportunistic refactors.
- Preserve unrelated dirty changes. Never overwrite work you did not make.
- Keep secrets, generated outputs, and runtime directories out of tracked files.
- Do not access validation or holdout data before the promotion gates allow it,
  and never use their results to guide discovery.
- Completed aggregation states become knowable at the interval end. No lookahead.
- Keep the canonical alpha row narrow. Prices, returns, costs, positions, fills,
  and PnL belong in diagnostics or backtests.

## Verification

Use `uv` for Python commands. Run the checks relevant to the change:

```bash
uv sync
uv run python -m unittest discover -s tests
uv run python -m evolution --help
uv run python -m research.literature_registry --validate
git diff --check
```

`uv run python -m experiments.ma_crossing` needs live catalog access and is not
an offline check. Before reporting completion, confirm that only intended files
changed.
