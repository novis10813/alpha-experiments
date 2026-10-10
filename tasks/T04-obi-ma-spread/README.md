# T04: OBI MA Spread

This document describes how to reproduce [REPORT.md](REPORT.md).

## Data Window and Inputs

- Start: 2026-06-17T00:00:00Z
- End: 2026-06-18T00:00:00Z
- Instruments: `BTCUSDT.BINANCE`
- Alpha source: `tasks/T04-obi-ma-spread/obi_ma_spread_report.py`
- Price or diagnostic source: `outputs/market/kbar_orderbook_imbalance_BTCUSDT_2026-06-17_1m_complete.csv`
- Nautilus data type: `OrderBookDepth10` joined into complete 1 minute K-bar rows by `tasks.T04-obi-ma-spread.kbar_orderbook_imbalance`.

## Commands

Run all commands from the repository root.

### Build the K-bar + OBI Input CSV

```bash
uv run python -m tasks.T04-obi-ma-spread.kbar_orderbook_imbalance \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-06-17T00:00:00Z \
  --end 2026-06-18T00:00:00Z \
  --interval-seconds 60 \
  --orderbook-coverage-seconds 1 \
  --imbalance-basis mean \
  --output outputs/market/kbar_orderbook_imbalance_BTCUSDT_2026-06-17_1m_complete.csv
```

Writes `outputs/market/kbar_orderbook_imbalance_BTCUSDT_2026-06-17_1m_complete.csv`.

### Build the Event Study

```bash
uv run python -m tasks.T04-obi-ma-spread.obi_ma_spread_report \
  --source outputs/market/kbar_orderbook_imbalance_BTCUSDT_2026-06-17_1m_complete.csv \
  --short-window 5 \
  --long-window 15 \
  --horizons-minutes 1 3 5 10 15 30 \
  --cooldown-minutes 0 5 15 \
  --cost-bps 0 2 5 10 \
  --output outputs/reports/obi_ma_spread_BTCUSDT_2026-06-17.html
```

Writes the event study: `outputs/reports/obi_ma_spread_BTCUSDT_2026-06-17.html`.
