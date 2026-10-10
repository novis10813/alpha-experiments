# T08: Observation Studies A1-A3

This document describes how to reproduce [REPORT.md](REPORT.md).

## Data and setup

Common inputs: BTC, ETH, and BNB discovery folds 1-5 (2026-06-13 to 2026-07-12,
2026-07-01 missing) and the supplemental discovery splits (2026-08-29 to
2026-09-20), 51 days per instrument. Cost is the v1 spot profile (10 bps per fill)
unless stated. Mid-price returns, bid/ask fills in A3.

## Commands and outputs

Reproduce from the repository root with local discovery data under `data/`.
Run in this order, because later steps read earlier outputs:

```bash
uv run python -m tasks.T08-observation-studies.observe_a1_large_moves      # A1 -> outputs/observe-a1/
uv run python -m tasks.T08-observation-studies.observe_a2_precursors       # A2 -> outputs/observe-a2/
uv run python -m tasks.T08-observation-studies.observe_a2_conditional      # A2 conditional breakeven (stdout)
uv run python -m tasks.T08-observation-studies.observe_f9_fold4            # F9 (stdout)
uv run python -m tasks.T08-observation-studies.observe_a3_triple_barrier   # A3 -> outputs/observe-a3/
uv run python -m tasks.T08-observation-studies.observe_a3_recost           # A1 and A3 under draft v2 fees (stdout)
```

Each script's docstring records its preregistered definitions and pass rules.
