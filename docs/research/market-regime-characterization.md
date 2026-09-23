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
