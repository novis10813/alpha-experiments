# Research Notes

Durable research decisions: factor notes, evolution families, diagnostics,
protocols, and the literature registry. Start a session with
[Current Research Focus](current-focus.md). The research loop and vocabulary are
in the [Alpha Research Framework](research-framework.md).

## Index

| Area | Notes |
| --- | --- |
| Factors | [Order Book Imbalance Feature](factors/orderbook_imbalance_feature.md), [Down-Streak Pressure](factors/down_streak_pressure.md), [Five Green Streak](factors/five_green_streak.md), [OBI MA Spread](factors/obi_ma_spread.md) |
| Evolution families | [`families/`](families/) |
| Evolution protocol | [Evolution guide](openevolve-strategy-evolution.md), [Promotion Protocol](promotion-protocol.md), [Experiment Ledger](experiment-ledger.md), [Execution Cost Profile v2 (draft)](execution-cost-profile-v2.md) |
| Discovery diagnostics | [Harness Diagnostic](discovery-harness-diagnostic.md), [Execution Parity](execution-parity.md), [Cost and Delay Sensitivity](cost-delay-sensitivity.md), [Eligibility Gate Audit](eligibility-gate-audit.md), [Registered Entry Signal Diagnostic](registered-entry-signal-diagnostic.md) |
| Market regime | [Characterization](market-regime-characterization.md), [Classifier v2 Investigation](market-regime-classifier-v2-investigation.md) |
| Literature | [Registry](literature/README.md), [Scout Workflow](literature/scout-workflow.md) |
| Templates | [Factor note](templates/factor-research-template.md), [Literature note](templates/literature-note-template.md) |

## Factor status

One status per factor note. Evolution families use the separate statuses in the
[Promotion Protocol](promotion-protocol.md#research-statuses).

| Status | Meaning |
| --- | --- |
| `idea` | Written down, not evaluated. |
| `diagnostic_passed` | Data quality and signal diagnostics look usable. |
| `feature_candidate` | Measurable edge, better used as a feature, filter, state, or execution input than as a standalone alpha. |
| `backtest_candidate` | Strong enough to justify execution assumptions and strategy tests. |
| `rejected` | Evidence does not support further work under current assumptions. |
| `archived` | Superseded or paused, kept for context. |

## Note rules

- One factor per file under `factors/`, written from the
  [factor template](templates/factor-research-template.md).
- Record the data window, instrument, inputs, and the commands that regenerate
  every cited artifact.
- Link to generated reports. Do not copy large tables or embed generated HTML.
- Check the [literature registry](literature/README.md) before researching a
  new paper.
- When a bug or data issue changes a result, state the correction explicitly.
