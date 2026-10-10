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

`excursion-v3` adds an August discovery supplement, 2026-07-25 to 2026-08-28
(end exclusive: it starts at the holdout end and stops before the quarantined day
2026-08-28). It is built and audited from the catalog with

```bash
bash tasks/T09-vol-excursion/build_august.sh   # -> data/evolution-data-supplemental/discovery_supplemental_20260725_20260828/
```

Audits go to `outputs/evolution-diagnostics/supplemental-audit-discovery_supplemental_20260725_20260828-<symbol>.json`.
Data from 2026-09-21 onward is not built: it is reserved as out-of-sample.

## Commands and outputs

```bash
uv run python -m tasks.T09-vol-excursion.observe_excursion      # -> outputs/T09-vol-excursion/excursion-v1/
uv run python -m tasks.T09-vol-excursion.observe_continuation   # -> outputs/T09-vol-excursion/excursion-v2/
uv run python -m tasks.T09-vol-excursion.observe_flow_confirm   # -> outputs/T09-vol-excursion/excursion-v3/
```

| File | Content |
| --- | --- |
| `by_decile.csv` | Excursion quantiles, touch, both-side, up-first, time-to-touch, and endpoint rates per instrument, horizon, sampling, and rv_60 decile (decile 0 = all) |
| `checks.csv` | Preregistered checks C1 (magnitude) and C2 (direction) with per-block values |
| `samples_non_overlap.csv` | Non-overlapping samples behind the main table |
| `run.json` | Costs, thresholds, blocks, and dataset manifest hashes |

`excursion-v2` (`observe_continuation.py`) writes:

| File | Content |
| --- | --- |
| `events.csv` | One row per breakout event: side, decile at the breakout, continuation outcome, trade gross and net |
| `summary.csv` | Continuation rates and trade results per instrument, b, h, and group (all, decile 9-10) |
| `by_decile.csv` | The same per rv_60 decile |
| `checks.csv` | Preregistered checks C3 (direction) and C4 (economics) |

`excursion-v3` (`observe_flow_confirm.py`) writes:

| File | Content |
| --- | --- |
| `events.csv` | excursion-v2 events plus fade trade results and side-aligned flow and OBI at the breakout |
| `c5_direction.csv` | Continuation share for confirming and opposing flow or OBI, per instrument, feature, b, and h, with per-block differences |
| `c6_economics.csv` | Follow and fade trade results per instrument and config |
| `quintiles.csv` | Continuation share and net by quintile of the aligned feature (descriptive) |
| `checks.csv` | Preregistered checks C5 (direction) and C6 (economics) |

REPORT.md numbers come from `by_decile.csv` (`sample=non_overlap`, columns
`p_touch_v1x2`, `p_end_v1x2`, `t_touch_med_v1x2`, `p_up_first_v1x2`, `p_touch_hl_v1x2`)
and `checks.csv` (C2 share = 0.5 + `pooled`).

excursion-v2 numbers come from its `summary.csv` (`k=2`, `group=dec9_10` for the
table, all rows for the ranges) and `checks.csv`. Breakeven continuation uses
round-trip cost 2 x 5 bps.
