# Research Notes

This directory records factor research findings and the commands needed to
reproduce them. Keep these notes focused on conclusions, assumptions, data
windows, and links to local report artifacts. Large CSV and HTML outputs should
stay under `outputs/`.

Use [Current Research Focus](current-focus.md) as the entry point for a new
research session. Use [Alpha Research Framework](research-framework.md) as the
operating model for new research. The current focus is hypothesis-based and
rule-based alpha research before prediction-oriented modeling.

## Directory Layout

```text
docs/research/
  README.md
  current-focus.md
  research-framework.md
  factors/
    <factor_name>.md
  templates/
    factor-research-template.md
```

## Factor Status

Use one status per factor note:

| Status | Meaning |
| --- | --- |
| `idea` | Concept has been written down but not evaluated. |
| `diagnostic_passed` | Basic data quality and signal diagnostics look usable. |
| `feature_candidate` | Signal has measurable edge but is better suited as a model feature, filter, state, or execution input; this does not imply a tradable standalone alpha. |
| `backtest_candidate` | Signal is strong enough to justify execution assumptions and strategy tests. |
| `rejected` | Evidence does not support further work under current assumptions. |
| `archived` | Superseded or paused; kept for historical context. |

## Maintenance Rules

- Keep one factor per file under `docs/research/factors/`.
- Use `docs/research/templates/factor-research-template.md` for new factor notes.
- Record the data window, instrument, input files, report files, and commands.
- Link to generated reports, but do not copy large tables or embed generated HTML.
- Keep the canonical alpha row shape in `docs/alpha-signal-format.md`; research
  notes can describe diagnostics derived from that shape.
- If a result changes because a bug or data issue was found, keep the correction
  explicit in the factor note.

## Current Factors

| Factor | Status | Summary |
| --- | --- | --- |
| [Order Book Imbalance Feature](factors/orderbook_imbalance_feature.md) | `feature_candidate` | Directional short-horizon signal exists, but observed edge is small after fixing sparse price data. |
| [Down-Streak Pressure](factors/down_streak_pressure.md) | `feature_candidate` | Down-down-down 1m kbar streaks with confirmed sell pressure show conditional downside continuation, but edge weakens after costs and de-overlap. |
