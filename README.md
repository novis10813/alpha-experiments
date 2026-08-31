# Alpha Experiments

A local research repository for hypothesis-based alpha experiments on Nautilus
Trader market data. The repository helps turn observable market states into
alpha rows, diagnostics, and carefully bounded evolution experiments. It does
not claim that a feature or research result is a tradable alpha.

## Start here

- [Repository guide](docs/repository-guide.md): directory map, data boundaries,
  local artifacts, and verified commands.
- [Roadmap](docs/ROADMAP.md): staged research and engineering work.
- [Current research focus](docs/research/current-focus.md): what to pursue or
  avoid next.
- [Alpha research framework](docs/research/research-framework.md): vocabulary
  and the minimum research loop.
- [Alpha signal format](docs/alpha-signal-format.md): canonical row shape and
  timestamp rules.

## Setup and tests

```bash
uv sync
uv run python -m unittest discover -s tests
```

Catalog-backed commands need the runtime settings described in
[`data/README.md`](data/README.md). Keep credentials outside tracked files.

## Local artifacts

`outputs/`, `.local/`, `.pi/`, and `.worktrees/` contain local generated or runtime
material. Do not commit or document their contents; verify ignore coverage before
adding a new artifact path. Keep validation and holdout data behind the
machine-enforced evolution gates.
