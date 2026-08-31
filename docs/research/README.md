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
  factors/       factor notes and status decisions
  families/      evolution hypothesis preregistrations
  templates/     factor and literature note templates
  literature/    verified source registry and paper notes
  *.md           diagnostics, protocols, ledgers, and evolution notes
```

The code that supports these notes lives in `reports/`, `data/`, `research/`, and
`evolution/`. Generated CSV, HTML, and image artifacts stay under `outputs/`.

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
- Use the [Literature and Hypothesis Registry](literature/README.md) for verified
  source metadata and proposed source-grounded hypotheses. Check it before
  researching a new paper.
- Record the data window, instrument, input files, report files, and commands.
- Link to generated reports, but do not copy large tables or embed generated HTML.
- Keep the canonical alpha row shape in `docs/alpha-signal-format.md`; research
  notes can describe diagnostics derived from that shape.
- If a result changes because a bug or data issue was found, keep the correction
  explicit in the factor note.

## Current Factor Index

The current notes cover four factor lines. Two remain `feature_candidate`: [Order
Book Imbalance Feature](factors/orderbook_imbalance_feature.md) is a
microstructure feature or filter with a small short-horizon effect, and
[Down-Streak Pressure](factors/down_streak_pressure.md) is an instrument-specific
BTC filter candidate whose edge weakens after costs and de-overlap. Two remain
`idea`: [Five Green Streak](factors/five_green_streak.md) and [Order Book
Imbalance MA Spread](factors/obi_ma_spread.md). Both need stronger confirmation
or more stable diagnostics before strategy work.

The [family notes](families/) preregister current evolution lineages. The
[diagnostic and protocol notes](./) record discovery-only harness checks,
execution parity, cost and delay sensitivity, eligibility, promotion, and the
local experiment ledger. Use [Current Research Focus](current-focus.md) to
choose the next line of work rather than treating the index as a promotion list.
