# T05: Evolution Credibility

This document describes how to reproduce [REPORT.md](REPORT.md). All commands run from the repository root.

## Discovery Harness Diagnostic

Run the report with:

```bash
uv run python -m evolution diagnose \
  --instrument-id BTCUSDT.BINANCE \
  --run-id milestone-1-1-v1
```

The command reads only the five split names registered in `DISCOVERY_FOLDS`. It rejects
validation, holdout, and unknown split names.

The diagnostic uses the five registered discovery folds and the fixed flat, buy-and-hold,
SMA 3/8, and SMA 60/240 initial-program baselines. The default dataset root is
`data/evolution-data`. The command writes
`outputs/evolution-diagnostics/btcusdt/milestone-1-1-v1/diagnostic.json`.

## Discovery Execution Parity

The inputs are fast discovery datasets and the exported smoke-run candidates:
BTC `smoke-20260830-06`, ETH `smoke-20260830-01`, and BNB `smoke-20260830-01`.
Both profiles use the five registered discovery folds.

Build one-second discovery data:

```bash
uv run python -m evolution build-executable-discovery \
  --instrument-id BTCUSDT.BINANCE
```

Rerank exported candidates:

```bash
uv run python -m evolution rerank \
  --instrument-id BTCUSDT.BINANCE \
  --run-id smoke-20260830-06 \
  --top-n 10
```

Generated `rerank.json` files remain under `outputs/evolution/`. They are local artifacts;
this note is the durable research record.

The build reads `data/evolution-data` and writes one-second discovery datasets under
`data/evolution-data-executable`. The rerank command reads those two dataset roots and
the exported candidates under `outputs/evolution/btcusdt/smoke-20260830-06/`, then writes
`outputs/evolution/btcusdt/smoke-20260830-06/rerank.json`.

## Discovery Cost and Delay Sensitivity

The source diagnostic does not record a reproduction command. Its inputs are the
three executable discovery champions, the same five discovery folds, one-second quotes,
minute states, position sizing, and strategy code. The scenarios use fees of 0, 5, 10,
and 15 bps and delays of 0, 1, and 5 seconds; the official profile is 10 bps and one second.

The official sensitivity scenario reproduced each `rerank.json` executable aggregate
exactly. A mismatch would invalidate the sensitivity report.

## Discovery Eligibility Gate Audit

The source diagnostic does not record a reproduction command. The inputs are the
three 30-iteration smoke checkpoints.

The policy now lives in `evolution/eligibility.py`. Eligibility evaluation returns
structured rejection reasons instead of silently replacing the score without an audit
category.
