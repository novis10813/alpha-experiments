# Current Research Focus

Entry point for a new research session. Updated 2026-10-07.

## Current state

- **Cost is the binding constraint.** Discovery-only observation studies A1-A3
  ([experiment ledger](experiment-ledger.md#observation-studies)) measured the
  directional hit rate needed to break even. Under the v1 spot profile (20 bps
  round trip) it exceeds 1.0 at 15 minutes or less and 0.90 at 30 minutes. Under
  perpetual taker fees (10 bps round trip) it is 0.79 to 0.88 at 15 minutes,
  0.70 to 0.76 at 30 minutes, 0.64 to 0.69 at 60 minutes, and 0.57 to 0.59 at
  240 minutes.
- **Large moves are predictable in size, not direction.** Volatility clustering
  and the UTC 13-15 window predict large 30 and 60 minute moves on all three
  instruments. No tested feature predicts their direction.
- **A3 rejected.** The 4h reversal after a large 24h move earned 0 to 7 bps gross
  per trade under triple-barrier exits, below both spot and perpetual taker cost.
- **Minute-pooled diagnostics overstate edge.** Decile spreads computed on
  overlapping minutes were 2 to 5 times the per-trade gross edge of
  non-overlapping first-trigger trades. Judge candidates on per-trade results.
- **Data does not match the venue.** The target venue is Binance USDⓈ-M
  perpetuals, but the catalog holds spot data only. Spot microstructure features
  (OBI, signed flow, spread) may lag perpetual price discovery.
- **Cost profile v2 is drafted, not active.** See
  [Execution Cost Profile v2](execution-cost-profile-v2.md).
- **Milestone 1 smoke champions** remain negative under the official profile and
  at 5 bps per fill. None may access validation.
- **Market regime map** (rule v2) is generated. See
  [Market Regime Characterization](market-regime-characterization.md).

## Paused research lines

These lines target horizons of 30 minutes or less, where breakeven needs a 70%
or higher directional hit rate even under perpetual taker fees. Resume one only
with a hypothesis that also selects large-move periods or uses a longer horizon.

| Line | Last status |
| --- | --- |
| [Down-Streak Pressure](factors/down_streak_pressure.md) | `feature_candidate`, BTC-only, 30 minute edge thin after cost and de-overlap |
| [Five Green Streak](factors/five_green_streak.md) | `idea`, weak continuation that did not survive cost |
| [OBI MA Spread](factors/obi_ma_spread.md) | `idea`, small and unstable after cooldown and cost |

[Order Book Imbalance](factors/orderbook_imbalance_feature.md) stays a
`feature_candidate` for filters and execution timing. Do not add more raw
imbalance reports.

## Next useful work

1. **Add perpetual data (D2).** Binance USDⓈ-M trades, depth, and funding in the
   homestack catalog builder, outside this repository.
2. **Activate cost profile v2 (D1).** Complete its activation checklist, then
   implement it as a separate change.
3. **New hypotheses from observation.** Work on discovery data only, count every
   look in the experiment ledger, and register a mechanism before testing.
   Target horizons of 240 minutes or more, or signals that select large-move
   periods. Evaluate per trade with triple-barrier exits.
4. **Maker execution (D3)** only after a tradable signal exists. It needs
   tick-level queue and fill simulation.

## Avoid

- Pure direction signals at 30 minutes or less.
- Promoting any raw feature to a backtest without per-trade, cost-inclusive
  evidence.
- Treating instrument-specific results as universal.
- Prediction-oriented modeling before rule candidates and diagnostic targets
  exist.

## Read first

1. [Alpha Research Framework](research-framework.md)
2. [Experiment Ledger](experiment-ledger.md)
3. [Execution Cost Profile v2](execution-cost-profile-v2.md)
4. [Promotion Protocol](promotion-protocol.md)

The full list of notes is in the [research index](README.md).
