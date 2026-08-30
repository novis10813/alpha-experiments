# Five Green Streak

## Status

`idea`

## Definition

- Alpha name: `five_green_streak_1m`
- Formula: emit a bullish event when the current 1 minute K-bar and the previous four consecutive 1 minute K-bars are all bullish (`close > open`).
- Nautilus data type: trade ticks converted to 1 minute trade-price K-bars.
- Instrument universe: start with `BTCUSDT.BINANCE`, then compare `ETHUSDT.BINANCE` and `BNBUSDT.BINANCE`.
- Timestamp semantics: the event is known only when the fifth bullish 1 minute K-bar closes, so `ts_event` is the fifth bar end time.

## Data Window

- Start: 2026-05-25
- End: 2026-06-25
- Instruments: `ETHUSDT.BINANCE`, `BNBUSDT.BINANCE`
- Alpha source: `reports/five_green_streak_report.py`.
- Price or diagnostic source: 1 second trade-price CSV with `ts_event,instrument_id,price`.
- Row counts: 20,161 1 minute K-bars per instrument.

## Commands

```bash
uv run python -m data.trade_prices \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-06-11T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --no-downsample \
  --output outputs/market/trade_prices_BTCUSDT_2026-06-11_2026-06-25_raw.csv

uv run python -m reports.five_green_streak_report \
  --price-source outputs/market/trade_prices_BTCUSDT_2026-06-11_2026-06-25_raw.csv \
  --horizons-minutes 1 3 5 10 30 \
  --cooldown-minutes 0 5 30 \
  --cost-bps 0 2 5 10 \
  --output outputs/reports/five_green_streak_BTCUSDT_2026-06-11_2026-06-25.html
```

## Reports

- Event study:
  - `outputs/reports/five_green_streak_ETHUSDT_2026-05-25_2026-06-25.html`
  - `outputs/reports/five_green_streak_BNBUSDT_2026-05-25_2026-06-25.html`
- Relationship report: not applicable for first pass.
- Other diagnostics: compare against unconditional 1m K-bar forward returns if the first event study looks promising.

## Key Findings

- ETH had 443 raw events, 246 events after a 5 minute cooldown, and 192 events after a 30 minute cooldown.
- BNB had 489 raw events, 268 events after a 5 minute cooldown, and 202 events after a 30 minute cooldown.
- ETH showed weak positive gross continuation only at longer horizons. With no cooldown and no cost, mean gross return was -0.00067% at 1 minute, -0.00339% at 3 minutes, 0.00580% at 5 minutes, 0.02138% at 10 minutes, and 0.04666% at 30 minutes. After 5 bps cost, even the 30 minute no-cooldown mean net return was -0.00334%.
- ETH with a 30 minute cooldown had 0.03209% mean gross return at 30 minutes and a 53.65% gross hit rate, but became negative after 5 bps cost.
- BNB did not show useful continuation. With no cooldown and no cost, mean gross return was -0.00056% at 1 minute, 0.00099% at 3 minutes, 0.00436% at 5 minutes, 0.00571% at 10 minutes, and 0.00067% at 30 minutes. All tested horizons were negative after 2 bps cost except none.
- BNB with a 30 minute cooldown remained weak: 0.00725% mean gross return at 10 minutes and 0.00140% at 30 minutes, both negative after 2 bps cost.

## Interpretation

Treat this as a weak K-line feature candidate rather than a standalone alpha. The first-pass result does not support trading five consecutive bullish 1 minute K-bars by itself.

The rule may still be useful as a setup state for a second-stage filter. ETH has a small longer-horizon continuation shape, but it is not strong enough after simple cost assumptions. BNB mostly rejects the standalone continuation hypothesis.

The first-pass standard is:

- event count is large enough after a 5 minute or 30 minute cooldown;
- mean and median forward returns are positive at relevant horizons;
- hit rate is meaningfully above the unconditional baseline;
- results do not disappear under 2 to 10 bps cost assumptions.

## Caveats

- Transaction costs are only approximated as fixed bps in the diagnostic.
- Execution assumptions are not modeled.
- Consecutive bullish runs can create adjacent duplicate events; cooldown summaries are required.
- The rule uses completed 1 minute K-bars only and should not be evaluated before the fifth bar closes.

## Next Experiments

- Add order book imbalance as a confirmation layer only after the pure K-line rule has measurable structure.
- Compare five-green continuation against three-green and four-green variants.
- Split by large fifth-bar range, close location, and recent volatility regime.
- Test whether five green bars followed by a sixth-bar pullback has better continuation than immediate entry at the fifth close.
