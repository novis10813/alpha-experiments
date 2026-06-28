# Alpha Research Framework

This repository currently prioritizes hypothesis-based and rule-based alpha
research. The main goal is to turn explicit market-structure ideas into
testable signals, diagnostics, and research conclusions before introducing a
prediction layer.

## Research Approach

Start from a concrete hypothesis:

```text
When market condition X is observable at ts_event, future behavior Y should be
more likely over horizon Z.
```

Examples:

- When bid depth is much larger than ask depth, short-horizon returns should
  skew upward.
- When order book pressure and signed trade flow agree, continuation should be
  stronger.
- When a down move persists for several bars and sell pressure remains
  confirmed, downside continuation should be more likely.

The first pass should be a transparent rule or state definition. Avoid treating a
raw feature as a tradable alpha before testing whether it survives realistic
diagnostics.

## Vocabulary

- `raw feature`: A directly observed or derived market variable, such as order
  book imbalance, spread, trade density, signed trade flow, or recent return.
- `state`: A named market condition built from one or more raw features, such as
  high spread, dense trading, confirmed pressure, or absorption.
- `rule alpha`: A deterministic signal produced from a hypothesis or state
  definition. It should be knowable at `ts_event` and must not use forward
  returns, fills, PnL, or future information.
- `diagnostic`: A derived analysis output used to judge a feature or rule alpha,
  such as forward returns, executable returns, hit rates, regime summaries, or
  event tables.
- `backtest`: A strategy simulation with explicit position, execution, risk, and
  PnL assumptions.

Use these terms carefully. A variable with measurable directional information is
not automatically a tradable alpha.

## Minimum Research Loop

For a new hypothesis, prefer this sequence:

1. Define the observable signal or state.
2. Export canonical alpha rows only if the signal is a candidate rule alpha.
3. Run data quality checks and simple distribution diagnostics.
4. Test forward returns over relevant horizons.
5. Check sparse-data, lookahead, timestamp, and resampling assumptions.
6. Test realistic execution where applicable, especially bid/ask entry and exit,
   delay, spread, and transaction-cost sensitivity.
7. Split by plausible regimes only when they map to a market-structure reason.
8. Document whether the result is a standalone alpha, feature candidate,
   execution input, filter, or rejected idea.

Keep diagnostics separate from canonical alpha rows. Forward returns,
thresholds, z-scores, trigger flags, fills, positions, PnL, and drawdown belong
in reports, diagnostics, or backtests unless a derived dataset is explicitly
requested.

## Promotion Criteria

A hypothesis can be treated as a feature candidate when:

- The signal is observable at `ts_event`.
- The effect has a plausible market-structure explanation.
- Basic diagnostics show stable ordering, event behavior, or regime behavior.
- The result is not explained by a data-quality issue, sparse joins, or
  lookahead.

A rule alpha should only become a backtest candidate when:

- The effect is large enough to matter after realistic execution assumptions.
- Results are not dominated by adjacent duplicate events.
- Delay and transaction-cost sensitivity are understood.
- The rule can be expressed without future labels or report-only diagnostics.
- The intended use is clear: entry signal, filter, sizing input, or execution
  timing signal.

If the effect is small after executable-return checks, keep it as a feature or
filter candidate rather than forcing it into a trading strategy.

## Report Design

Reports should answer one research question at a time. Prefer focused report
builders over broad generic pipelines.

Good report questions:

- Does this signal rank future returns?
- Does this event type have directional follow-through?
- Does the edge survive bid/ask execution and cost?
- Does a regime strengthen or weaken the hypothesis?
- Are results robust across instruments or data windows?

Avoid reports that only add more charts without changing the decision about the
hypothesis.

## Output Handling

Treat `outputs/` as a local scratch area. Generated CSV, HTML, and image files
should be reproducible from commands recorded in research notes. Do not commit
large generated outputs.

Research notes should preserve:

- hypothesis and signal definition
- data window and instrument
- commands needed to regenerate important artifacts
- key numeric results
- final interpretation and status

When an experiment is complete, clean `outputs/` unless there is a specific
reason to keep local artifacts temporarily.

## Current Direction

For now, this repository should stay centered on hypothesis-based and rule-based
research. Prediction-oriented modeling can come later, after there are clear
rule alphas, feature candidates, and diagnostic targets worth predicting.
