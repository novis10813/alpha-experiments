# T07: Market Regime

## Market Regime Characterization

Status: discovery-only diagnostic. Not a factor, not a hypothesis acceptance,
and no fitness, ranking, or promotion use.

Characterizes daily market regimes (volatility x trend x direction) across the
registered discovery folds and the supplemental discovery splits, and
documents the extended discovery calendar that ROADMAP 2.6 requires before
"extended discovery covers more than one market regime" can be checked.

### Scope

- Discovery-only diagnostic. Regime labels are never used as candidate inputs,
  fitness terms, ranking features, or promotion-gate evidence.
- Inputs are local discovery split files only: no catalog access, no network,
  no validation or holdout data or results anywhere in this note or its
  artifacts.
- Regime math uses only `close` and `ts_event` from `EvolutionMarketState`.

### Preregistered rules (2026-09-21)

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

#### Rule selection rationale

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

### Preregistered rules v2 (2026-09-29)

Replaces the 2026-09-21 decision rule. The 12-label vocabulary
`<vol>_<trend>_<direction>` and the timestamping discipline are unchanged. The
v1 rule's structural defects (unreachable 2x-median efficiency threshold when
the trailing efficiency median exceeds 0.5; single-day trend/direction
statistics; 30-day anchor lag) are addressed as follows. Motivation and
evidence: [Market Regime Classifier v2 Investigation](#market-regime-classifier-v2-investigation).

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

#### v2 on the current sample (2026-09-29, descriptive only)

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

### Input observations

Data gaps observed in the inputs:

- 2026-07-01 is absent from all three instruments' `discovery_4` (manifest
  `missing_bucket_count: 1440`); the following day 2026-07-02 has null `r_d`
  and is reported `no_baseline`.
- Three days per instrument are `no_baseline` in total: the sample-start day
  2026-06-13 (no prior day), 2026-06-14 (its only prior day has no `r_d`), and
  2026-08-29 (first day after the fold/supplemental gap; prior day absent).
- The quarantined day 2026-08-28 is not present in any input split.

### Extended discovery calendar

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

## Market Regime Classifier v2 Investigation

Status: v2 rule implemented 2026-09-29 (map schema_version 2, v2 preregistration in
[Market Regime Characterization](#market-regime-characterization)). Evaluation (section 6) is deferred until
the data prerequisite (section 4.7) is met. Nothing in this note is a
hypothesis acceptance; no fitness, ranking, or promotion use.

### 1. Verdict on the current classifier

The classifier (`classify_days`, 12-label
`<vol>_<trend>_<direction>` grid, 30-day trailing medians, daily batch) is a
**coverage diagnostic** and does that job cleanly:

- Timestamp discipline is correct: interval-end day index (L158), strictly
  trailing baselines (L331-333), missing prior day -> `no_baseline` (no
  forward-fill), insufficient days excluded from baselines. No-lookahead is
  test-enforced (`test_future_day_does_not_change_earlier_labels`).
- Deterministic, offline, Nautilus-object-only, byte-reproducible. No alpha-row
  consumer exists yet (grep-verified); the only forward hook is ROADMAP 2.2.

What is structurally lacking:

1. **No predictive track record.** No forward-return association, no
   persistence/turnover measurement, no stability diagnostics have ever been
   computed. It has never been shown to separate forward returns or forward vol.
2. **Unreachable trend threshold.** `eff_d >= 2x median(trailing eff_d)` is
   impossible whenever the trailing efficiency median exceeds 0.5 (efficiency is
   bounded by 1.0). In strongly trending months the trend axis silently
   collapses to "never trending" (acknowledged in the characterization note).
3. **Un-pinned choices.** The 2x multiplier and 30-day window have no source or
   selection rule; any baseline comparison is confounded by free threshold
   choice.
4. **Too-slow response.** The note itself records that regime shifts in the
   literature move faster than a 30-day trailing baseline tracks.
5. **Single-day granularity.** Both the trend test and the direction use one
   day of returns; one-day crypto returns are noise, which is how knife-edge
   labels and the 2026-07-01-style gaps arise.
6. **Sample too thin to evaluate.** 51 UTC days per instrument locally
   (2026-06-13..07-12 + 08-29..09-20). No honest walk-forward is possible yet.

Verdict: keep the file, the label vocabulary, the split table, and the
timestamping discipline. **Replace the decision rule and preregister it. Do not
tune the existing rule — its flaws are structural, not parametric.**

### 2. What the survey found

Method survey (ranked for practitioner backtesting on daily/hourly crypto bars):

1. **Gaussian HMM (2-4 states)** on (return, realized vol, trend), walk-forward
   refit, causal filtered decoding only — most documented crypto regime model
   with verified OOS forecast value (Koki et al. 2020); known leakage/label
   switching have standard fixes.
2. **Volatility-band regimes + directional filter** — most robust and cheapest
   layer; strongest verified OOS evidence in the risk domain (Ardia et al. 2018
   OOS VaR; Ma et al. 2020 OOS RV).
3. **Bayesian online changepoint / CUSUM as RESET trigger** — O(1) cost,
   distribution-agnostic "something broke" detector matching how crypto shifts
   (shocks, not drifts).
4. **Offline PELT segmentation as a diagnostic** — objective map of when the
   distribution actually changed; sanity-check for the other detectors.
5. **Gradient-boosted classifier** — only category with verified OOS costed
   trading PnL (Sebastiao & Godinho 2021; Sharpe claims of ~80-91 should be
   discounted), but only as a layer on a simpler regime definition, not a
   primary detector.

Cross-cutting warnings: leakage (HMM smoothing, overlapping windows,
full-sample fits) is the #1 backtest trap; crypto vol level-shifts across years,
so fixed vol bands go stale; calibrate on 2022+ data, not pre-perp-birth
dynamics; sample breaks at 2019/2020-21/2021-05/2022/2024 mean per-segment
evaluation.

Signal catalog (crypto-specific inputs, evidence from papers/practitioner
sources; full table in the run store): funding rates (8h, Binance history to
2019), open interest (hourly, vendor history shallow), BTC dominance (daily),
stablecoin flows (DefiLlama daily since 2017), on-chain activity (daily,
retro-labeled wallets are a trap), cross-asset/macro (slow priors only, EOD
lookahead is the top failure mode), halving cycle (4-state prior, Glassnode
framework). Practitioners structure crypto regimes as (a) MS-vol states, (b)
non-homogeneous HMM with exogenous predictors (Koki et al. 2020), (c)
bull/bear x cross-asset linkage, (d) on-chain/halving cycle phase machine,
(e) macro-vol regime + positioning overlay (funding/OI/liquidations). Two-level
hierarchies (slow environment x fast state) are the common practitioner shape.

Evaluation protocol (full version in the run store): ex-post forward labels
with deadband as ground truth; walk-forward with purge = forward horizon for
stateful models; decision metrics = conditional forward-return lift net of a
cost grid {0, 5, 10, 15, 25} bps, Brier/log-loss vs a 3-class forward label,
duration/turnover, transition matrix; paired stationary bootstrap (B=2000) for
comparisons; decision on one preregistered primary cell + BH FDR across the
reported matrix + Harvey-Liu-Zhu t >= 3; simplicity guard (prefer the simpler
model when CIs overlap).

### 3. Scored shortlist

Fit = repo constraints (local splits, offline, Nautilus objects, no new heavy
deps — pyproject has 3 lines today); Evid = verified crypto OOS evidence; Eff =
5 for ~1 focused session; Interp/Robust per the audit's design intent.

```
ID  Candidate                                             Fit Evid Eff Interp Robust Total
--  ----------------------------------------------------  --- ---- --- ------ ------ -----
A   Rule v2: re-anchored vol band x 3-day trend w/        5   4    5   5      4      23
    hysteresis x deadband direction + CUSUM break flag
D   CUSUM/BOCPD reset layer (standalone)                  5   2    5   4      4      20
B   Gaussian HMM K=3, walk-forward, filtering only,       3   4    3   3      3      16
    pooled across instruments
C   2-state MS-GARCH on daily returns                     2   5    2   3      3      15
E   GBM/ensemble on handcrafted features                  2   3    2   2      2      11
```

- **A (Rule v2)** — in-family upgrade of the current classifier. Fixes all three
  structural defects; closes-only input (immune to the BNB schema-1 extended
  field trap); stdlib-only; every label a named per-day statistic. Its 2-axis x
  direction grid is not itself validated, hence Evid 4 not 5.
- **D** — cheapest "something broke" detector; the survey is explicit that
  changepoint methods have NO verified standalone OOS economic value and do not
  label bull/bear, so it earns its place as a flag layer inside A, not as the
  classifier.
- **B** — strongest documented method; blocked by dependency policy
  (hmmlearn or hand-rolled 3-state EM), label switching, and statistical
  non-viability on the current 51-day sample (small-sample over-segmentation).
- **C** — the single strongest verified OOS risk result (Ardia et al. 2018) but
  the most correctness surface; no direction axis; deferred.
- **E** — needs regime labels from A or B as training targets and a much larger
  sample; deferred.

### 4. Recommendation: Rule v2 (candidate A)

Deterministic, rule-based regime calendar; stdlib-only; daily batch; identical
operating model to today.

#### 4.1 Label set

Unchanged 12-label vocabulary `<vol>_<trend>_<direction>` with
vol in {high, low}, trend in {trending, non_trending}, direction in {up, down,
flat}; statuses `classified` / `no_baseline` / `insufficient_data` unchanged.
New per-day **diagnostic only**: boolean `break_flag` (CUSUM). Flags never
change labels or baselines; they mark anchor staleness for humans and for
evaluation diagnostics. Keeping the 12-label space keeps the existing coverage
tables comparable.

#### 4.2 Inputs (closes only, per UTC day d; complete = >= 600 closes)

- `r_d`: `close_d / close_{d-1e} - 1` (previous complete day; null ->
  `no_baseline`, no forward-fill; unchanged).
- `R3_d`: 3-day cumulative return, `close_d / close_{d-3e} - 1`, where d-3e is
  the 3rd most recent complete day at or before d (calendar gaps tolerated; all
  involved days complete).
- `sigma_d`: sample stdev of 1-min log returns on day d, x sqrt(525600)
  (unchanged).
- `eff3_d`: Kaufman efficiency over the 3-day span,
  `|close_d - close_{d-3e}| / sum|1-min dclose|` over the span (bounded in
  (0,1], but over a path long enough that one noisy minute cannot dominate).
- `z_d`: robust z of `sigma_d` vs the strictly prior 90-day window:
  `0.6745 * (sigma_d - median) / MAD`.

#### 4.3 Decision rules (single named function `classify_days_v2`)

Trailing statistics use the up-to-90 complete days strictly before d (floor 30;
fewer -> `no_baseline`). All windows strictly trailing; the existing
no-lookahead test suite carries over.

- **Vol axis:** `high_vol` iff `sigma_d >= median(trailing 90d sigma)`.
  Candidate anchors {median/90d, median/60d} preregistered, selected on train
  only.
- **Trend axis (hysteresis):** enter trending iff `|R3_d| >= 2.0 * median
  (trailing |R3|) AND eff3_d >= q75(trailing eff3)`; exit trending iff
  `|R3_d| < 1.0 * median(trailing |R3|)`. Candidate sets: entry multiplier
  {1.5, 2, 3}, exit {1.0, 1.5}, efficiency quantile {q50, q75, q90}. The
  q75-of-own-distribution efficiency threshold is always reachable, fixing the
  documented 2x-median defect.
- **Direction (deadband):** `flat` iff `|R3_d| <= 0.5 * sd(trailing R3)`;
  up/down by sign otherwise. Candidate deadbands {0.25, 0.5}.
- **Break flag (diagnostic only):** two-sided CUSUM on `z_d`:
  `S+ = max(0, S+ + z_d - k)`, `S- = min(0, S- - z_d - k)`; `break_flag` iff
  `max(S+, -S-) > h`, then reset both to 0. Candidate k {0.5, 1.0}, h {4, 6}.
- **Selection rule:** every candidate-set choice made on the training window
  only, before any test fold is looked at; the primary variant values above
  carry the decision.

#### 4.4 Timestamping and cadence

Daily batch, offline, deterministic. Label for day d uses only data with
`ts_event <= end of day d`; R3/eff3 span only complete days; every trailing
statistic strictly prior to d. Knowable at end of day d — no lookahead.

#### 4.5 Alpha-row consumption

**Now: none.** The classifier stays a discovery-only diagnostic with no code
consumer; nothing enters any alpha row, fitness term, or promotion gate until
section 6 passes and the promotion protocol is invoked.

**If it graduates:** a new alpha module emits exactly
`(ts_event, instrument_id, alpha_name, value)`:
`ts_event` = end of the labeled UTC day; `alpha_name` = `market_regime_v2`;
`value` = action in {+1, 0, -1} via the protocol's common decision mapping
(training-window median 1-day forward return per state: top third -> +1, bottom
third -> -1, else 0). Everything else — features, trailing statistics, CUSUM
path, `break_flag`, per-day quadrant — stays in diagnostics:
the regime map (schema_version 1 -> 2, add per-day feature block + flags +
anchor values) and this note family.

#### 4.7 Data prerequisite (verify Day 0)

Only 51 days/instrument are local. Assumption: the read-only catalog has 1-min
history to at least mid-2025. Action: build supplemental discovery splits targeting >= 365 UTC
days ending 2026-09-20, respecting the supplemental discovery guards
(exclude validation 2026-07-12..07-18, holdout 2026-07-18..07-25, quarantined
2026-08-28). Without >= ~120 days the 90-day anchor is meaningless and section 6
cannot start. If depth is unavailable: fix defects #2 and #5 of section 1 on
the 51-day sample as a documented improvement and defer all evaluation claims —
say so in the preregistration.

### 5. Fallback (runner-up): 3-state Gaussian HMM, pooled across instruments

Frozen design: features `(r_d, sigma_d, eff3_d)` standardized on train only;
K = 3 preregistered, no K-scan on test; rolling W = 180 days, one fit per fold
(20 random restarts, fixed seed, best loglik recorded); **filtering (forward)
decoding only — full-sample Viterbi or sliced smoothing is banned** (the #1
leakage trap); states sorted by (mean, vol) after each fit; refit-stability
check (shift +3 days, disagreement > 30% -> FRAGILE); action mapping per the
protocol. Dependency decision (hmmlearn vs ~150-line hand-rolled stdlib EM)
made Day 0 and recorded in the preregistration.

Switch A -> B only if ALL hold: (T1) >= 365 days available; (T2) A fails the
falsification tests **structurally** — CHATTER (median state duration < 2 days)
or STALE flags in a strict majority of folds despite hysteresis, or vol axis
passes but trend/direction add no net lift and the HMM beats A's mapping on
paired-bootstrap Brier with the 90% CI excluding 0; (T3) B itself passes the
decision rules including the +1 bps/day economic floor with directional
consistency on >= 2 of 3 majors. Before switching families, first collapse A to
a 4-label vol x direction variant (simplicity guard) and re-evaluate.

### 6. Evaluation plan

Apply the evaluation protocol to A with two documented preregistered deviations
forced by local data depth: warmup 730d -> 180d; rolling train window W 365d ->
180d. Everything else per protocol: 21-day contiguous folds post-warmup on
BTC/ETH/BNB; primary label = 1-day forward return with deadband; cost grid
{0, 5, 10, 15, 25} bps with official c0 = 10 bps; baselines always reported:
w = 0, w = sign(trailing 30d return), and w = 1{forward volq LOW} as a
**ceiling benchmark** (it uses the forward label), not a must-beat baseline.
Paired stationary bootstrap, B = 2000, L_b = 7 days; decision on the
preregistered primary cell (BTC, h = 1d, c0 = 10 bps) + BH q < 0.10 across the
matrix + Harvey-Liu-Zhu t >= 3 + directional consistency on >= 2 of 3 majors.
Compute: well under 2 hours; human cost ~1-2 focused sessions.

**Falsification** — outcomes that kill the recommendation:

- **F1 (directional):** on the primary cell, A's cumnet(10 bps) <= 0 in a
  strict majority of valid folds, or the paired-bootstrap 90% CI vs the best
  naive proxy fails the +1 bps/day economic floor.
- **F2 (vol axis):** pooled test-forward 7-day variance ratio
  V_HIGH / V_LOW < 1.2 — the classifier fails even as a risk filter,
  falsifying the strongest evidence pillar behind the design on our data.
- **F3 (instability):** CHATTER/STALE/FRAGILE flags on decision states in a
  strict majority of folds after hysteresis.

Partial-failure exit (honest, not a rerun): F1 without F2 -> demote A to a
vol-only 4-label sizing filter (high/low vol x direction) for position sizing,
matching the survey's finding that vol regimes monetize via risk management
rather than standalone directional PnL.

### 7. Risks

- **R1 Small-sample fragility.** Even 365 days is one market slice; a 21-day
  fold holds only ~3-4 independent regime episodes. Early warning: > 30% void
  folds, any decision state with < 100 bars in a fold, effective episode count
  < 4, lift sign flipping across folds. If any fires: no decision on that cell;
  extend splits or shrink the claim.
- **R2 Anchor lag after a true structural break.** The 90-day trailing anchors
  inherit the old regime; a 2022-scale shift mislabels the new regime for
  ~90 days. The map records both 30-day and 90-day anchors per day so this can
  be diffed. Alert: `break_flag` fires and 30d/90d anchors disagree on the vol
  decision for > 14 consecutive days, or high_vol rate stuck > 90% or < 10% for
  30 days. Response: mark the span untrusted; shorten or break-reset the anchor
  in a versioned preregistered change.
- **R3 Lookahead regression at future consumption.** The v2 math is strictly
  trailing and unit-tested; the realistic failure is in consumers (ROADMAP 2.2
  state machine, a live reimplementation reading stale timestamps, classifying
  partial days). Guard: the existing `test_future_day_does_not_change_earlier_labels`
  stays green on every change (red = protocol violation, not test failure);
  the Day-1 point-in-time audit (50 random bars recomputed from raw data
  truncated at t) reruns on every schema bump; any new consumer passes its own
  cutoff-diff test before wiring beyond diagnostics.

### 8. Key references (from the surveys)

- Ardia, Bluteau, Rueder — regime changes in Bitcoin GARCH volatility (FRL
  2019, doi:10.1016/j.frl.2018.08.009) — OOS VaR improvement, 304+ cites.
- Koki, Leonardos, Piliouras — Exploring the Predictability of Cryptocurrencies
  via Bayesian HMMs (arXiv:2011.03741, 2020) — non-homogeneous HMM with
  crypto-specific predictors; OOS predictive density vs random walk.
- Ma et al. (2020) — OOS realized-vol forecasting with vol regimes.
- Sebastiao & Godinho (2021) — ensemble agreement regime rules, OOS costed PnL
  (Sharpe ~80-91 claims discounted).
- Koch et al. (2024) — plain GARCH/SV can beat MS-GARCH OOS; distribution shift
  documented 2017-2021 vs 2022+.
- Takaishi (2021) — multifractal vol distribution shift across crypto eras.
- Lopez de Prado (2018) — purged k-fold + embargo.
- Harvey, Liu, Zhu (2016) — t > 3 hurdle.
- Benjamini & Hochberg (1995) — FDR; Politis & Romano (1994) — stationary
  bootstrap.
- Glassnode on-chain cycle framework; Amberdata macro-vol + positioning
  snapshot (practitioner regime constructions).

Full per-method evidence, per-signal availability tables, and the complete
evaluation protocol text are in the workflow run store, not duplicated here.

### 9. Next steps

1. Day 0: verify catalog 1-min depth (>= 365 days ending 2026-09-20) and build
   the supplemental discovery splits (requires catalog env vars).
2. Write the implementation spec for Rule v2 (this note section 4 is the
   content) and implement in the classifier + tests, then
   write the dated v2 preregistration.
3. Only after 1 and 2: run the section 6 evaluation with the Day-1 point-in-time
   audit first.
