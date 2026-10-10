# T01: Order Book Imbalance Feature

This document describes how to reproduce [REPORT.md](REPORT.md). All commands
run from the repository root.

## Data window and inputs

- Instrument: `BTCUSDT.BINANCE`
- Start: `2026-06-18T00:00:00Z`
- End: `2026-06-25T00:00:00Z`
- Nautilus data type: `OrderBookDepth10`

## Reproduce

Generated files follow
`outputs/{alphas,market,reports}/<name>_BTCUSDT_2026-06-18_2026-06-25*.{csv,html}`.
Commands for the 1 second quote export and the quote-executable, spread-regime,
clustered-extreme, and dense-signed-flow screens were not recorded.

Generate the alpha:

```bash
uv run python -m alphas.orderbook_imbalance \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-06-18T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --output outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv
```

Generate 1 second last trade prices:

```bash
uv run python -m scripts.trade_prices \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-06-18T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --resample-seconds 1 \
  --output outputs/market/trade_prices_BTCUSDT_2026-06-18_2026-06-25_1s.csv
```

Generate relationship reports:

```bash
uv run python -m tasks.T01-orderbook-imbalance.alpha_relationship_report \
  outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv \
  --price-source outputs/market/trade_prices_BTCUSDT_2026-06-18_2026-06-25_1s.csv \
  --output outputs/reports/orderbook_imbalance_relationship_BTCUSDT_2026-06-18_2026-06-25_10s_1s_prices.html \
  --horizons-seconds 10 \
  --bucket-count 10 \
  --max-points 8000
```

Repeat with `--horizons-seconds 30` and `--horizons-seconds 60` for the other
relationship reports.

Generate the extreme imbalance event study:

```bash
uv run python -m tasks.T01-orderbook-imbalance.extreme_imbalance_report \
  outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv \
  --price-source outputs/market/trade_prices_BTCUSDT_2026-06-18_2026-06-25_1s.csv \
  --output outputs/reports/orderbook_imbalance_extreme_BTCUSDT_2026-06-18_2026-06-25.html \
  --thresholds 0.95 0.98 \
  --horizons-seconds 1 5 10 30 60
```

Generate 1 second trade price and volume features:

```bash
uv run python -m scripts.trade_features \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-06-18T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --resample-seconds 1 \
  --output outputs/market/trade_features_BTCUSDT_2026-06-18_2026-06-25_1s.csv
```

Generate the volume interaction report:

```bash
uv run python -m tasks.T01-orderbook-imbalance.volume_interaction_report \
  outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv \
  --feature-source outputs/market/trade_features_BTCUSDT_2026-06-18_2026-06-25_1s.csv \
  --output outputs/reports/orderbook_imbalance_volume_interaction_BTCUSDT_2026-06-18_2026-06-25_30s.html \
  --horizons-seconds 30 \
  --bucket-count 10 \
  --max-points 8000
```

Generate the trade density regime report:

```bash
uv run python -m tasks.T01-orderbook-imbalance.trade_density_report \
  outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv \
  --feature-source outputs/market/trade_features_BTCUSDT_2026-06-18_2026-06-25_1s_with_count.csv \
  --output outputs/reports/orderbook_imbalance_trade_density_BTCUSDT_2026-06-18_2026-06-25.html \
  --horizons-seconds 10 30 60 \
  --bucket-count 10
```

Generate 1 second signed trade features:

```bash
uv run python -m scripts.trade_features \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-06-18T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --resample-seconds 1 \
  --output outputs/market/trade_features_BTCUSDT_2026-06-18_2026-06-25_1s_signed.csv
```

Generate signed flow absorption reports:

```bash
uv run python -m tasks.T01-orderbook-imbalance.signed_flow_absorption_report \
  outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv \
  --feature-source outputs/market/trade_features_BTCUSDT_2026-06-18_2026-06-25_1s_signed.csv \
  --output outputs/reports/orderbook_imbalance_signed_flow_absorption_BTCUSDT_2026-06-18_2026-06-25.html \
  --horizons-seconds 10 30 60
```

Repeat with `--flow-column volume_imbalance` and output
`outputs/reports/orderbook_imbalance_signed_volume_absorption_BTCUSDT_2026-06-18_2026-06-25.html`
for signed volume flow.

Generate 1 minute confirmed pressure persistence:

```bash
uv run python -m alphas.pressure_persistence \
  outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv \
  --feature-source outputs/market/trade_features_BTCUSDT_2026-06-18_2026-06-25_1s_signed.csv \
  --bucket-seconds 60 \
  --output outputs/alphas/confirmed_pressure_persistence_BTCUSDT_2026-06-18_2026-06-25_1m.csv
```

Generate the 1m/3m/5m relationship report:

```bash
uv run python -m tasks.T01-orderbook-imbalance.alpha_relationship_report \
  outputs/alphas/confirmed_pressure_persistence_BTCUSDT_2026-06-18_2026-06-25_1m.csv \
  --price-source outputs/market/trade_prices_BTCUSDT_2026-06-18_2026-06-25_1s.csv \
  --output outputs/reports/confirmed_pressure_persistence_relationship_BTCUSDT_2026-06-18_2026-06-25_1m_3m_5m.html \
  --horizons-seconds 60 180 300 \
  --bucket-count 10 \
  --max-points 8000
```

Repeat with `--flow-column volume_imbalance`,
`--alpha-name confirmed_volume_pressure_persistence_1m`, and output
`outputs/alphas/confirmed_volume_pressure_persistence_BTCUSDT_2026-06-18_2026-06-25_1m.csv`
for the signed volume version.
