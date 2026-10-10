# T09: Volatility State and Forward Excursion

This document describes how to reproduce [REPORT.md](REPORT.md).

## Data and setup

BTC, ETH, and BNB discovery folds 1-5 (2026-06-13 to 2026-07-12, 2026-07-01
missing) and the supplemental discovery splits (2026-08-29 to 2026-09-20), the
same inputs as [T08](../T08-observation-studies/README.md). Split roots are listed
in [T07](../T07-market-regime/README.md#characterization-inputs-and-data-window).
No catalog access, validation, or holdout data is needed.

Definitions, thresholds, and the preregistered checks are in the docstring of
`observe_excursion.py`.

## Commands and outputs

```bash
uv run python -m tasks.T09-vol-excursion.observe_excursion   # -> outputs/T09-vol-excursion/excursion-v1/
```

| File | Content |
| --- | --- |
| `by_decile.csv` | Excursion quantiles, touch, both-side, up-first, time-to-touch, and endpoint rates per instrument, horizon, sampling, and rv_60 decile (decile 0 = all) |
| `checks.csv` | Preregistered checks C1 (magnitude) and C2 (direction) with per-block values |
| `samples_non_overlap.csv` | Non-overlapping samples behind the main table |
| `run.json` | Costs, thresholds, blocks, and dataset manifest hashes |

REPORT.md numbers come from `by_decile.csv` (`sample=non_overlap`, columns
`p_touch_v1x2`, `p_end_v1x2`, `t_touch_med_v1x2`, `p_up_first_v1x2`, `p_touch_hl_v1x2`)
and `checks.csv` (C2 share = 0.5 + `pooled`).
