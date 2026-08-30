# Order Book Imbalance MA Spread

## Status

`idea`

## Definition

- Alpha name: `orderbook_imbalance_ma_spread_5m_15m`
- Formula: `rolling_mean(orderbook_imbalance_mean, 5) - rolling_mean(orderbook_imbalance_mean, 15)`.
- Nautilus data type: `OrderBookDepth10` joined into complete 1 minute K-bar rows by `data.kbar_orderbook_imbalance`.
- Instrument universe: first pass on `BTCUSDT.BINANCE`.
- Timestamp semantics: the signal is known at the 1 minute K-bar end time after the latest bar's order book samples are complete.

## Data Window

- Start: 2026-06-17T00:00:00Z
- End: 2026-06-18T00:00:00Z
- Instruments: `BTCUSDT.BINANCE`
- Alpha source: `reports/obi_ma_spread_report.py`
- Price or diagnostic source: `outputs/market/kbar_orderbook_imbalance_BTCUSDT_2026-06-17_1m_complete.csv`
- Row counts: 1,439 complete 1 minute K-bar plus OBI rows; 1,425 rolling signals.

## Commands

```bash
uv run python -m reports.obi_ma_spread_report \
  --source outputs/market/kbar_orderbook_imbalance_BTCUSDT_2026-06-17_1m_complete.csv \
  --short-window 5 \
  --long-window 15 \
  --horizons-minutes 1 3 5 10 15 30 \
  --cooldown-minutes 0 5 15 \
  --cost-bps 0 2 5 10 \
  --output outputs/reports/obi_ma_spread_BTCUSDT_2026-06-17.html
```

## Reports

- Event study: `outputs/reports/obi_ma_spread_BTCUSDT_2026-06-17.html`

## Key Findings

- `spread_positive` (`obi_5m_mean > obi_15m_mean`) produced 707 raw events, 183 events after a 5 minute cooldown, and 80 events after a 15 minute cooldown.
- `spread_positive_short_positive` (`obi_5m_mean > obi_15m_mean and obi_5m_mean > 0`) produced 488 raw events, 134 events after a 5 minute cooldown, and 67 events after a 15 minute cooldown.
- The broad `spread_positive` group was not bullish on this sample. With no cooldown and no cost, mean gross return was -0.00117% at 1 minute, -0.00544% at 3 minutes, -0.00935% at 5 minutes, -0.02048% at 10 minutes, -0.02880% at 15 minutes, and -0.04447% at 30 minutes.
- The stricter `spread_positive_short_positive` group was less bad and showed some 30 minute gross continuation. With no cooldown and no cost, mean gross return was 0.00197% at 1 minute, -0.00423% at 3 minutes, -0.00604% at 5 minutes, -0.00250% at 10 minutes, 0.00128% at 15 minutes, and 0.02294% at 30 minutes.
- After a 5 minute cooldown, the stricter group had 0.02722% mean gross return at 30 minutes and 0.00722% net after 2 bps cost, but became negative after 5 bps cost.
- After a 15 minute cooldown, the stricter group's 30 minute result disappeared: -0.00294% mean gross return.

## Interpretation

Treat `obi_5m_mean > obi_15m_mean` as an unproven and weak OBI momentum feature, not as a standalone long alpha.

The first pass rejects the simple version where short-term OBI merely rises above longer-term OBI. Requiring the short-term OBI mean to also be positive improves the result, but the edge is small, unstable under cooldown, and not robust to 5 bps cost.

## Caveats

- This first pass only uses one BTC trading day.
- Transaction costs are approximated as fixed bps in the diagnostic.
- Execution assumptions are not modeled.
- The 30 minute result can be sensitive to broader intraday trend and overlapping event exposure.

## Next Experiments

- Run the same report on a longer BTC window once complete kbar+OBI rows are available.
- Add a minimum spread threshold, such as `obi_5m_mean - obi_15m_mean > 0.05`, instead of any positive crossover.
- Test cross-up events only, where the spread moves from non-positive to positive, rather than every positive state bar.
- Combine the stricter OBI condition with K-line state, such as five-green, range expansion, or pullback-after-five-green.
