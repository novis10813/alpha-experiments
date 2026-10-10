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

### vol-gate-v1

Adds an August discovery supplement, 2026-07-25 to 2026-08-28 (end exclusive: it
starts at the holdout end and stops before the quarantined day 2026-08-28). Build
and audit it from the catalog once:

```bash
bash tasks/T09-vol-excursion/build_august.sh   # -> data/evolution-data-supplemental/discovery_supplemental_20260725_20260828/
```

Data from 2026-09-21 onward is not built: it is reserved as out-of-sample.
Definitions are in the docstring of `observe_vol_gate.py`.

```bash
uv run python -m tasks.T09-vol-excursion.observe_vol_gate          # -> outputs/T09-vol-excursion/vol-gate-v1/
uv run python -m tasks.T09-vol-excursion.plot_vol_gate summary     # -> outputs/T09-vol-excursion/vol-gate-v1/figures/
uv run python -m tasks.T09-vol-excursion.plot_vol_gate window --inst BTC --start 2026-08-01 --end 2026-08-03 --h 60 --threshold 40
```

| File | Content |
| --- | --- |
| `o1_ic.csv` | Daily and pooled Spearman IC of each estimator with \|r_h\| and R, per instrument and h |
| `o1_bins.csv` | Mean \|r_h\| with day-bootstrap interval, mean R, net, and p* per x bin, with per-block means |
| `o1_gate.csv` | The same for minutes with x >= X, per threshold X, with open share overall and per block |
| `o3_ic.csv` | Daily partial IC of other instruments' sigma with \|r_h\|, controlling own sigma |
| `o3_heat.csv` | Mean \|r_h\| on own x by source x bins |
| `o4_z.csv` | Quantiles of R / x and \|r_h\| / x per x bin |
| `features_<inst>.parquet` | Minute mid, high, low, and the six estimators |
| `run.json` | Costs, bins, blocks, and dataset manifest hashes |

REPORT.md figures are copied from `figures/` (`F2_bins_rv_60`, `F3_gate_v1`,
`F3_gate_v2`, `F4_daily_ic`, `F6_z_rv_60`). Tables use estimator `rv_60`: daily IC
from `o1_ic.csv` (`ic_mean`, `ic_ir`, `ic_pos_share`, `ic_pooled`), lowest p* per
instrument and h < 240 from `o1_bins.csv` (`p_star_v1`, `p_star_v2`), gate
thresholds as the first `X` with `p_star_v1 <= 0.75` or `p_star_v2 <= 0.65` in
`o1_gate.csv` (`coverage` is the open share), median ratios from `o4_z.csv`
(`z_abs_q50`), and cross-instrument IC from `o3_ic.csv`.
