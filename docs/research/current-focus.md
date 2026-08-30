# Current Research Focus

This file is the entry point for a new research session.

## Current State

- The raw order book imbalance research line is complete for now.
- Raw `orderbook_imbalance_depth10` should be treated as a microstructure
  feature, filter, or execution-timing input, not as a standalone tradable alpha.
- The most relevant follow-on rule candidate from that line is
  [Down-Streak Pressure](factors/down_streak_pressure.md).
- Down-streak pressure is instrument-specific: BTC has the clearest conditional
  continuation structure, ETH rejected the structure in validation, and BNB only
  showed a thin 30 minute signed-volume regime effect.
- Pure 1 minute five-green-streak continuation is a weak K-line feature
  candidate, not a standalone alpha. ETH showed only small longer-horizon gross
  continuation that did not survive simple cost assumptions, and BNB mostly
  rejected the standalone continuation hypothesis.
- One-day BTC testing of `orderbook_imbalance_ma_spread_5m_15m` rejected the
  broad condition `obi_5m_mean > obi_15m_mean` as a standalone bullish rule.
  Requiring `obi_5m_mean > 0` improved the shape, but the result remained small
  and unstable after cooldown and cost checks.
- Generated artifacts in `outputs/` are scratch files. Durable findings should
  live in factor notes under `docs/research/factors/` or in focused experiment
  notes under `docs/research/`.
- Milestone 1 experiment-credibility work is complete. Fast discovery may
  generate and screen candidates, but executable discovery with one-second
  quotes, a one-second delay, and 10 bps fees determines final discovery rank.
  Machine-enforced qualification blocks unqualified candidates before validation
  loading, and family-level locks protect holdout use.
- All three smoke-run executable champions remained negative under the official
  profile. BTC and ETH are cost-fragile, while BNB remains negative before fees.
  None may access validation.

## Next Useful Work

Choose one of these before writing more code:

- Continue down-streak pressure only as a BTC-focused or BNB signed-volume
  30-minute regime/filter candidate.
- Refine down-streak pressure with explicit volatility, trade-density, and broad
  market trend gates before considering any backtest or quote-based execution
  screen.
- If continuing K-line research, refine
  [Five Green Streak](factors/five_green_streak.md) only with additional state
  filters such as fifth-bar range, close location, volatility regime, pullback
  entry, or order book confirmation.
- If continuing OBI moving-average research, refine
  [Order Book Imbalance MA Spread](factors/obi_ma_spread.md) with cross-up
  events, minimum spread thresholds, longer BTC windows, and K-line state
  confirmation before considering a backtest.
- Start a new hypothesis-based factor note using
  [Alpha Research Framework](research-framework.md) and the factor template.
- Begin Milestone 2 with hypothesis-specific seed lineages. Use the Milestone 1
  findings to define failure modes and search constraints, but do not feed full
  discovery reports or scenario tables back into candidate prompts.

## Avoid For Now

- Do not add more raw order book imbalance reports unless there is a specific
  new hypothesis that existing reports do not answer.
- Do not promote raw order book imbalance to a backtest candidate.
- Do not promote pure five-green-streak continuation to a backtest candidate
  without a stronger confirmation layer.
- Do not promote raw `obi_5m_mean > obi_15m_mean` to a long-only backtest
  candidate.
- Do not treat down-streak pressure as a universal cross-instrument rule.
- Do not start prediction-oriented modeling until there are clearer rule
  candidates, feature candidates, and diagnostic targets worth predicting.

## Read First

For a new session, read these in order:

1. [Alpha Research Framework](research-framework.md)
2. [Order Book Imbalance Feature](factors/orderbook_imbalance_feature.md)
3. [Down-Streak Pressure](factors/down_streak_pressure.md)
4. [Five Green Streak](factors/five_green_streak.md)
5. [Order Book Imbalance MA Spread](factors/obi_ma_spread.md)
6. [Discovery Harness Diagnostic](discovery-harness-diagnostic.md)
7. [Discovery Execution Parity](execution-parity.md)
8. [Cost and Delay Sensitivity](cost-delay-sensitivity.md)
9. [Eligibility Gate Audit](eligibility-gate-audit.md)
10. [Evolution Promotion Protocol](promotion-protocol.md)
11. [Literature and Hypothesis Registry](literature/README.md)
12. [Alpha Signal Format](../alpha-signal-format.md)
