# Current Research Focus

This file is the entry point for a new research session.

## Current State

- The raw order book imbalance research line is complete for now.
- Raw `orderbook_imbalance_depth10` should be treated as a microstructure
  feature, filter, or execution-timing input, not as a standalone tradable alpha.
- The most relevant follow-on rule candidate from that line is
  [Down-Streak Pressure](factors/down_streak_pressure.md).
- Generated artifacts in `outputs/` are scratch files. Durable findings should
  live in factor notes under `docs/research/factors/`.

## Next Useful Work

Choose one of these before writing more code:

- Continue the down-streak pressure line by testing whether it persists on ETH
  and BNB, then decide whether it remains instrument-specific.
- Refine down-streak pressure with explicit volatility, trade-density, and broad
  market trend gates before considering any backtest.
- Start a new hypothesis-based factor note using
  [Alpha Research Framework](research-framework.md) and the factor template.

## Avoid For Now

- Do not add more raw order book imbalance reports unless there is a specific
  new hypothesis that existing reports do not answer.
- Do not promote raw order book imbalance to a backtest candidate.
- Do not start prediction-oriented modeling until there are clearer rule
  candidates, feature candidates, and diagnostic targets worth predicting.

## Read First

For a new session, read these in order:

1. [Alpha Research Framework](research-framework.md)
2. [Order Book Imbalance Feature](factors/orderbook_imbalance_feature.md)
3. [Down-Streak Pressure](factors/down_streak_pressure.md)
4. [Alpha Signal Format](../alpha-signal-format.md)
