# Alpha Experiments

Local alpha research on Binance BTCUSDT, ETHUSDT, and BNBUSDT market data, built
on Nautilus Trader. Hypotheses are tested on discovery data. Validation and
holdout splits stay behind machine-enforced promotion gates.

## Start here

- [Repository guide](AGENTS.md): layout, data and artifact rules,
  and commands.
- [Current research focus](docs/research/current-focus.md): research state and
  next work.
- [Research framework](docs/research/research-framework.md): vocabulary and the
  research loop.

## Setup

```bash
uv sync
uv run python -m unittest discover -s tests
```

Catalog-backed commands need the settings in [`AGENTS.md`](AGENTS.md#data-and-outputs).
