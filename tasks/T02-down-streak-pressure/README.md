# T02: Down-Streak Pressure

This document describes how to reproduce [REPORT.md](REPORT.md).

## Data Windows And Inputs

The initial 7 day diagnostic uses `BTCUSDT.BINANCE` from
`2026-06-18T00:00:00Z` to `2026-06-25T00:00:00Z`. The longer stability
and cross-instrument requests run from `2026-05-25T00:00:00Z` to
`2026-06-25T00:00:00Z`, using BTC, ETH, and BNB. See the
[Data Windows](REPORT.md#data-windows) section for returned catalog coverage.

## Running From The Repository Root

Run all commands below from the repository root. Input and output files are
specified by the source and output arguments in each command.

## Commands

Generate the longer-window raw imbalance, prices, and signed trade features:

```bash
uv run python -m alphas.orderbook_imbalance \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-05-25T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --output outputs/alphas/orderbook_imbalance_BTCUSDT_2026-05-25_2026-06-25.csv

uv run python -m scripts.trade_prices \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-05-25T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --resample-seconds 1 \
  --output outputs/market/trade_prices_BTCUSDT_2026-05-25_2026-06-25_1s.csv

uv run python -m scripts.trade_features \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-05-25T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --resample-seconds 1 \
  --output outputs/market/trade_features_BTCUSDT_2026-05-25_2026-06-25_1s_signed.csv
```

Generate the down-streak pressure screens:

```bash
uv run python -m tasks.T02-down-streak-pressure.down_streak_pressure_report \
  --price-source outputs/market/trade_prices_BTCUSDT_2026-05-25_2026-06-25_1s.csv \
  --pressure-source outputs/alphas/confirmed_pressure_persistence_BTCUSDT_2026-06-11_2026-06-25_1m.csv \
  --feature-source outputs/market/trade_features_BTCUSDT_2026-05-25_2026-06-25_1s_signed.csv \
  --horizons-minutes 5 10 30 \
  --pressure-threshold 0.2 \
  --cooldown-minutes 0 5 30 \
  --cost-bps 0 2 5 10 \
  --output outputs/reports/down_streak_pressure_trade_count_BTCUSDT_2026-06-11_2026-06-25.html
```

Repeat with
`outputs/alphas/confirmed_volume_pressure_persistence_BTCUSDT_2026-06-11_2026-06-25_1m.csv`
and output
`outputs/reports/down_streak_pressure_volume_BTCUSDT_2026-06-11_2026-06-25.html`
for the signed-volume pressure version.

For ETH and BNB, repeat the same commands with the symbol-specific sources:

```bash
uv run python -m tasks.T02-down-streak-pressure.down_streak_pressure_report \
  --price-source outputs/market/trade_prices_ETHUSDT_2026-05-25_2026-06-25_1s.csv \
  --pressure-source outputs/alphas/confirmed_pressure_persistence_ETHUSDT_2026-06-11_2026-06-25_1m.csv \
  --feature-source outputs/market/trade_features_ETHUSDT_2026-05-25_2026-06-25_1s_signed.csv \
  --horizons-minutes 5 10 30 \
  --pressure-threshold 0.2 \
  --cooldown-minutes 0 5 30 \
  --cost-bps 0 2 5 10 \
  --output outputs/reports/down_streak_pressure_trade_count_ETHUSDT_2026-06-11_2026-06-25.html
```

Repeat for `BNBUSDT`, and repeat both symbols with the corresponding
`confirmed_volume_pressure_persistence` source for the signed-volume pressure
version.
