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

## Outputs and Notes

Artifact rules are in the [repository guide](../../AGENTS.md#data-and-outputs).
Note rules are in [Note rules](#note-rules).

## Factor status

One status per factor note. Evolution families use the separate statuses in the
[Promotion Protocol](../../evolution/docs/promotion-protocol.md#research-statuses).

| Status | Meaning |
| --- | --- |
| `idea` | Written down, not evaluated. |
| `diagnostic_passed` | Data quality and signal diagnostics look usable. |
| `feature_candidate` | Measurable edge, better used as a feature, filter, state, or execution input than as a standalone alpha. |
| `backtest_candidate` | Strong enough to justify execution assumptions and strategy tests. |
| `rejected` | Evidence does not support further work under current assumptions. |
| `archived` | Superseded or paused, kept for context. |

## Note rules

- One factor per `tasks/T<NN>-<name>/REPORT.md`, written from the
  [factor template](templates/factor-research-template.md).
- Record the data window, instrument, and inputs in `REPORT.md`, and the commands
  that regenerate every cited artifact in the task's `README.md`.
- Link to generated reports from the task's `README.md`. Do not copy large tables
  or embed generated HTML.
- Check the [literature registry](literature/README.md) before researching a
  new paper.
- When a bug or data issue changes a result, state the correction explicitly.
- Record rejected and inconclusive results. Negative results are part of the
  research history.
