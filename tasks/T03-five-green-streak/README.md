# T03: Five Green Streak

This document describes how to reproduce [REPORT.md](REPORT.md).

## Data Window and Inputs

- Start: 2026-05-25
- End: 2026-06-25
- Instruments: `ETHUSDT.BINANCE`, `BNBUSDT.BINANCE`
- Alpha source: `tasks/T03-five-green-streak/five_green_streak_report.py`.
- Price or diagnostic source: 1 second trade-price CSV with `ts_event,instrument_id,price`.

## Commands

Run all commands from the repository root. The recorded commands use `BTCUSDT.BINANCE` for 2026-06-11 through 2026-06-25.

```bash
uv run python -m scripts.trade_prices \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-06-11T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --no-downsample \
  --output outputs/market/trade_prices_BTCUSDT_2026-06-11_2026-06-25_raw.csv

uv run python -m tasks.T03-five-green-streak.five_green_streak_report \
  --price-source outputs/market/trade_prices_BTCUSDT_2026-06-11_2026-06-25_raw.csv \
  --horizons-minutes 1 3 5 10 30 \
  --cooldown-minutes 0 5 30 \
  --cost-bps 0 2 5 10 \
  --output outputs/reports/five_green_streak_BTCUSDT_2026-06-11_2026-06-25.html
```

## Outputs

- The trade-price command writes `outputs/market/trade_prices_BTCUSDT_2026-06-11_2026-06-25_raw.csv`.
- The event-study command writes `outputs/reports/five_green_streak_BTCUSDT_2026-06-11_2026-06-25.html`.
- Recorded event-study reports:
  - `outputs/reports/five_green_streak_ETHUSDT_2026-05-25_2026-06-25.html`
  - `outputs/reports/five_green_streak_BNBUSDT_2026-05-25_2026-06-25.html`
