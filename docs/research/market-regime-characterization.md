# Market Regime Characterization

Status: discovery-only diagnostic. Not a factor, not a hypothesis acceptance,
and no fitness, ranking, or promotion use.

Characterizes daily market regimes (volatility x trend x direction) across the
registered discovery folds and the supplemental discovery splits, and
documents the extended discovery calendar that ROADMAP 2.6 requires before
"extended discovery covers more than one market regime" can be checked.

## Scope

- Discovery-only diagnostic. Regime labels are never used as candidate inputs,
  fitness terms, ranking features, or promotion-gate evidence.
- Inputs are local discovery split files only: no catalog access, no network,
  no validation or holdout data or results anywhere in this note or its
  artifacts.
- Regime math uses only `close` and `ts_event` from `EvolutionMarketState`.

## Preregistered rules (2026-09-21)

Superseded by the v2 rules below (2026-09-29) — retained for the v1 calendar
recorded in this note.

Per UTC day, per instrument; trailing-only baselines, no lookahead:

- Complete day: at least 600 one-minute closes. Days below the threshold are
  reported as `insufficient_data` and excluded from baselines.
- `r_d`: simple daily return, `close(last minute of d) / close(last minute of
  d-1) - 1`. Null when the previous UTC day is absent from the sample.
- `sigma_d`: sample standard deviation of one-minute log returns within day
  `d`, annualized by `sqrt(525600)`.
- `eff_d`: `|close_d - open_d| / sum(|one-minute close changes|)` within day
  `d` (Kaufman efficiency ratio at daily granularity). Null when the
  denominator is zero.
- Trailing baseline: the up-to-30 complete UTC days strictly before `d` (all
  available earlier complete days for the first 30 days).
- Vol regime: `high_vol` iff `sigma_d >= median(trailing sigma)`, else
  `low_vol`.
- Trend regime (rule C): `trending` iff `|r_d| >= 2 * median(trailing |r|)`
  AND `eff_d >= 2 * median(trailing eff)`, else `non_trending`.
- Direction: `up` / `down` / `flat` from the sign of `r_d`.
- Label: `<vol>_<trend>_<direction>`, e.g. `high_vol_trending_up`.

Calendar day of a state: `(ts_event - 60s) // 86400s`, because each one-minute
state's interval ends at `ts_event` (repository convention: completed
aggregation states become knowable at the interval end).

### Rule selection rationale

The plan left the trend axis open between candidate A (magnitude only), B
(path efficiency only), and C (both). A provisional literature pass on crypto
market regime practice (2026-09-21, sources not yet in the literature
registry) supported C:

- Magnitude-only (A) labels violent V-shaped reversal days as trending,
  although their net open-to-close displacement is small.
- Efficiency-only (B) labels small-range low-volatility drift days as
  trending, because the efficiency ratio approaches 1.0 on tiny smooth drift.
- Magnitude gated by path efficiency is the standard practitioner
  construction (e.g. Kaufman's efficiency ratio as a trend/noise filter). No
  peer-reviewed source was found that formalizes this exact daily crypto
  construction, so the rule is this repository's own preregistration.
- The 2x trailing-median multiplier is an engineering choice; no source pins
  down 2x versus 1.5x or percentile thresholds for this construction. 2x is
  the most conservative option in the plan. Caveat: `eff_d` is bounded by
  1.0, so in strongly trending months the trailing efficiency median can
  exceed 0.5 and the efficiency threshold becomes unreachable; the daily
  table records `eff_d` so the effect is visible, and the rule is a single
  named function (`trend_rule_c_magnitude_and_efficiency_2x_median`) so the
  map can be regenerated under a different rule without rework.
- Crypto regime literature that uses HMM or Markov-switching models finds
  regime shifts faster than a 30-day trailing baseline would track. That is a
  heavier alternative and is not used here because the calendar requires a
  single named deterministic rule.

## Preregistered rules v2 (2026-09-29)

Replaces the 2026-09-21 decision rule. The 12-label vocabulary
`<vol>_<trend>_<direction>` and the timestamping discipline are unchanged. The
v1 rule's structural defects (unreachable 2x-median efficiency threshold when
the trailing efficiency median exceeds 0.5; single-day trend/direction
statistics; 30-day anchor lag) are addressed as follows. Motivation and
evidence: `market-regime-classifier-v2-investigation.md`.

Per UTC day, per instrument; trailing-only baselines, no lookahead:

- Complete day: at least 600 one-minute closes (unchanged). Days below the
  threshold are `insufficient_data`, excluded from baselines, and leave the
  trend and CUSUM state unchanged.
- `r3_d`: 3-complete-day cumulative return, `close_d / close_base - 1`, where
  `base` is the 3rd-most-recent complete day at or before `d` (the span holds
  exactly 3 complete days; calendar gaps tolerated). Null when the span cannot
  be formed.
- `eff3_d`: `|close_d - close_base| / sum(one-minute path length over the same
  3 complete days)`. Null when the denominator is zero. (Unlike the v1
  within-day efficiency, `eff3` is not bounded by 1.0: the numerator includes
  day-boundary jumps that the within-day path denominator does not.)
- `sigma_d`: unchanged (one-minute log-return stdev, annualized by
  `sqrt(525600)`).
- Trailing baseline: the up-to-90 complete UTC days strictly before `d`.
  **New explicit floor:** fewer than 30 prior complete days -> `no_baseline`
  (v1 had no floor; on the current 51-day sample each instrument now
  classifies 21 of 51 days instead of 48 — an honest consequence of the
  longer anchor, not a regression).
- Vol regime: `high_vol` iff `sigma_d >= median(trailing sigma)`, else
  `low_vol` (window widened 30 -> 90 days).
- Trend regime (hysteresis): enter `trending` iff `|r3_d| >= 2.0 *
  median(trailing |r3|)` AND `eff3_d >= q75(trailing eff3)`; exit `trending`
  iff `|r3_d| < 1.0 * median(trailing |r3|)`. `q75` is the exclusive-method
  quartile (`statistics.quantiles(values, n=4)[2]`). The q75-of-own-
  distribution threshold is always reachable, fixing the v1 2x-median defect;
  the enter/exit gap stops flapping.
- Direction: `flat` iff `|r3_d| <= 0.5 * stdev(trailing r3)`; else `up`/`down`
  by sign of `r3_d` (deadband makes `flat` a real class on 3-day returns).
- `break_flag` (diagnostic only; never changes labels, baselines, or state
  beyond its own CUSUM state): two-sided CUSUM on the relative sigma deviation
  `d_d = (sigma_d - median_90d) / median_90d` with `k = 0.05`, `h = 4.0`,
  reset on trigger. **Deviation from the investigation note:** the note
  prescribed a MAD-based robust z, which degenerates to undefined (and the
  only sensible fallback, z = 0, makes the flag permanently blind) on a
  zero-dispersion trailing window. The relative deviation is scale-free, has
  no degenerate case (guard: median <= 0 -> no flag), and is hand-testable.
- Map schema: `schema_version` 2; per-day rows carry `r3`, `eff3`,
  `sigma_dev`, `break_flag`, and both the 30-day and 90-day sigma medians
  (anchor values recorded per day so anchor lag after a structural break can
  be diffed).

Candidate sets (primary variant above carries the decision): anchor window
{90, 60} days; trend entry {1.5, 2.0, 3.0} x median(|r3|); trend exit
{1.0, 1.5} x median(|r3|); efficiency quantile {0.50, 0.75, 0.90}; direction
deadband {0.25, 0.5} x stdev(r3); CUSUM k {0.05, 0.10}; CUSUM h {4.0, 6.0}.
Selection rule: every candidate-set choice is made on the training window
only, before any test fold is looked at. Selection is deferred to the
evaluation phase (investigation note section 6) and is NOT part of the
2026-09-29 implementation.

### v2 on the current sample (2026-09-29, descriptive only)

51 UTC days per instrument; 21 classified each (30-day floor). Discovery-only
diagnostics from the schema-2 map; NO inferential claims at this sample size
(see the evaluation protocol in the investigation note).

- Coverage: all four vol x trend quadrants now present on all three
  instruments (v1 was missing `low_vol_trending` for ETH).
- Persistence: trend axis stable (avg run 3.0-7.0 days, 3-7 transitions per
  instrument over 21 days — hysteresis working as intended). Vol axis
  CHATTER-adjacent: avg run 1.8-2.1 days (max 4), 10-12 transitions — at the
  protocol's CHATTER flag boundary (< 2 days). Structural cause: the 1x
  median threshold is a 50/50 split and the vol axis has no hysteresis.
- Forward-return association (1-day, pooled, n per cell 6-27; descriptive
  only): high_vol_non_trending n=18 mean -0.69% (std 1.97%);
  high_vol_trending n=9 mean +0.68% (2.49%); low_vol_non_trending n=27 mean
  +1.00% (2.61%); low_vol_trending n=6 mean +0.38% (1.21%). Vol-axis forward
  variance ratio V_HIGH/V_LOW ~= 0.83 — below the protocol's 1.2 line and
  inverted on this slice (no statistical power; recorded honestly).
- Direction axis is deadband-dominated: flat 44 of 60 forward-valid days
  (73%), up 14, down 2 — little information on this sample.
- break_flag: 0 on all 63 classified days.

Early-warning disposition (predefined, not ad hoc): if the vol-axis chatter
or the inverted variance separation persists on the >= 365-day extended
sample, the preregistered responses are (a) demote to the 4-label
vol x direction sizing filter, or (b) a versioned preregistration adding a
hysteresis band to the vol axis. No threshold tuning on this sample.

## Inputs

| Instrument | Original folds (2026-06-13..2026-07-12) | Supplemental (2026-08-29..2026-09-20) |
| --- | --- | --- |
| BTCUSDT.BINANCE | `.local/evolution-data-v2/discovery_1..5` (manifest schema 2) | `discovery_supplemental_20260829_20260830` + `discovery_supplemental_20260830_20260905` + `discovery_supplemental_20260905_20260921` |
| ETHUSDT.BINANCE | `.local/evolution-data-v2/discovery_1..5` (schema 2) | `discovery_supplemental_20260829_20260921` |
| BNBUSDT.BINANCE | `.local/evolution-data/discovery_1..5` (legacy root, schema 1) | `discovery_supplemental_20260829_20260921` |

Data gaps observed in the inputs:

- 2026-07-01 is absent from all three instruments' `discovery_4` (manifest
  `missing_bucket_count: 1440`); the following day 2026-07-02 has null `r_d`
  and is reported `no_baseline`.
- Three days per instrument are `no_baseline` in total: the sample-start day
  2026-06-13 (no prior day), 2026-06-14 (its only prior day has no `r_d`), and
  2026-08-29 (first day after the fold/supplemental gap; prior day absent).
- The quarantined day 2026-08-28 is not present in any input split.

## Extended discovery calendar

The calendar is the union of the eight registered discovery periods above
(five original folds plus three supplemental splits for BTC; five plus one
for ETH and BNB), each labeled with its regime coverage summary in the
generated map. Per-period coverage (classified days, by vol/trend quadrant):

| Instrument | Period | high_vol_trending | low_vol_trending | high_vol_non_trending | low_vol_non_trending |
| --- | --- | --- | --- | --- | --- |
| BTC | original folds (28 days) | 0 | 0 | 16 | 10 |
| BTC | supplemental (23 days) | 3 | 1 | 6 | 12 |
| ETH | original folds (28 days) | 0 | 0 | 11 | 15 |
| ETH | supplemental (23 days) | 3 | 0 | 6 | 13 |
| BNB | original folds (28 days) | 1 | 2 | 12 | 11 |
| BNB | supplemental (23 days) | 3 | 0 | 10 | 9 |

What the supplement adds:

- The original discovery folds contain almost no trending days: BTC and ETH
  have zero; BNB has three.
- The supplemental splits add trending coverage for all three instruments
  (BTC: `high_vol_trending_up` and `high_vol_trending_down` plus
  `low_vol_trending_down`; ETH: `high_vol_trending_up` and
  `high_vol_trending_down`; BNB: `high_vol_trending_up`, and
  `high_vol_trending_down` rises from one day to four).
- Combined, BTC and BNB cover all four vol/trend quadrants; ETH covers three
  (no `low_vol_trending` days in either period).

## Reproduction

```bash
uv run python -m reports.market_regime_report \
  --output outputs/evolution-diagnostics/market-regime-map.json
uv run python -m unittest tests.test_market_regime_report -v
```

The report runs offline (no catalog env required) and is deterministic: two
runs produce byte-identical JSON.

## Artifacts

- `outputs/evolution-diagnostics/market-regime-map.json` — per-day rows
  (date, return, sigma, efficiency, vol/trend/direction, label, source
  split), per-period coverage summaries, and split records with manifest
  bookkeeping.
- `reports/market_regime_report.py` — report code.
- `tests/test_market_regime_report.py` — synthetic-fixture tests covering
  hand-computable classification, trailing-only baselines, insufficient-day
  exclusion, and source-split attribution.
- Plan: `docs/superpowers/plans/2026-09-21-supplemental-data-market-regime.md`
  (Slice 2).
