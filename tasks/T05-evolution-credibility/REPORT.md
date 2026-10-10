# T05: Evolution Credibility

These are the Milestone 1 diagnostics of the evolution harness.

## Discovery Harness Diagnostic

### Status

Milestone 1.1 baseline diagnostic, discovery data only.

No validation or holdout dataset was read. These results diagnose the backtest harness
and do not qualify a strategy for promotion.

### Method

The diagnostic runs four fixed strategies independently on each of the five discovery
folds:

- flat
- buy-and-hold
- SMA 3/8
- the current SMA 60/240 initial program

Each fold starts with 100,000 USDT and resets the engine, strategy state, and position.
The backtest closes open positions when the fold stops. Aggregate return, fee drag, and
turnover are means across folds because each fold uses a separate starting account.
Trade and order counts are totals. Aggregate Sharpe uses the concatenated daily return
series.

Gross return equals net return plus reported commissions. Daily gross equity removes
commissions from the existing mark-to-market daily equity calculation while preserving
fill prices and bid-side marking for an open long position.

### Baseline results

Returns, fee drag, and turnover below are mean values per discovery fold. Closed
positions are totals across five folds.

| Instrument | Baseline | Gross return | Fee drag | Net return | Gross Sharpe | Net Sharpe | Closed positions | Turnover |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| BTCUSDT | Buy-and-hold | 0.0129% | 0.0200% | -0.0071% | 0.23 | -0.12 | 5 | 0.20x |
| BTCUSDT | Initial program | -0.0997% | 0.4444% | -0.5441% | -2.49 | -11.52 | 113 | 4.44x |
| BTCUSDT | SMA 3/8 | -0.0648% | 11.8043% | -11.8691% | -1.64 | -39.94 | 2,972 | 118.04x |
| ETHUSDT | Buy-and-hold | 0.1564% | 0.0202% | 0.1362% | 1.88 | 1.63 | 5 | 0.20x |
| ETHUSDT | Initial program | 0.0509% | 0.4437% | -0.3928% | 0.86 | -6.36 | 117 | 4.44x |
| ETHUSDT | SMA 3/8 | -0.0712% | 11.4657% | -11.5369% | -1.21 | -39.26 | 2,967 | 114.66x |
| BNBUSDT | Buy-and-hold | -0.1531% | 0.0158% | -0.1690% | -3.64 | -4.04 | 5 | 0.16x |
| BNBUSDT | Initial program | -0.0381% | 0.2658% | -0.3039% | -1.40 | -9.79 | 97 | 2.66x |
| BNBUSDT | SMA 3/8 | -0.2191% | 7.2230% | -7.4421% | -7.69 | -37.05 | 2,950 | 72.23x |

The flat strategy produced no orders, exposure, fees, turnover, or return for all three
instruments.

### Findings

The harness produces the expected accounting controls:

- flat stays at zero
- buy-and-hold opens and closes one position per fold
- gross return minus fee drag reconciles to net return
- forced fold-end exits appear in position counts and holding durations
- every fold uses an independent account and strategy instance

The initial program has two different failure modes. BTC and BNB lose money before fees,
then pay additional turnover costs. ETH has a small positive gross result, but 44 bps of
mean fee drag per fold turns it negative. The ETH result is diagnostic evidence of
turnover sensitivity, not alpha evidence.

SMA 3/8 trades close to once every several minutes while exposed and generates thousands
of round trips. Fees dominate its result on all three instruments. This baseline confirms
that the 10 bps fee model strongly penalizes noisy threshold switching.

Buy-and-hold confirms that discovery regimes differ by instrument. ETH rises over these
folds, BTC stays close to flat after fold resets, and BNB falls. A strategy comparison
must therefore retain per-fold and per-instrument results rather than infer one shared
market regime.

### Limits

This diagnostic still uses the current discovery execution model. It does not test the
one-second quote stream or execution delay used during promotion. It also covers fixed
baselines only; the smoke-run discovery candidates have not been loaded into this report.

The next step is Milestone 1.2: rerun these baselines on discovery data under coarse and
promotion-like execution assumptions, then measure the difference in fills, costs, and
net daily Sharpe.

<system-reminder>
The task tools haven't been used recently. If you're working on tasks that would benefit from tracking progress, consider using TaskCreate to add new tasks and TaskUpdate to update task status (set to in_progress when starting, completed when done). Also consider cleaning up the task list if it has become stale. Only use these if relevant to the current work. This is just a gentle reminder - ignore if not applicable. Make sure that you NEVER mention this reminder to the user
</system-reminder>

## Discovery Execution Parity

### Status

Milestone 1.2 complete. Discovery data only.

This analysis did not read validation or holdout datasets and did not inspect validation
or holdout results. None of the evaluated candidates qualifies for validation.

### Question

The OpenEvolve search used 60-second quotes with zero execution delay. Promotion uses
one-second quotes with a one-second delay. This analysis tests whether the faster
discovery model changes candidate performance or ranking when applied to the same five
discovery folds.

### Registered execution profiles

| Profile | Quote interval | Execution delay | Role |
|---|---:|---:|---|
| Fast discovery | 60 seconds | 0 seconds | Candidate generation and coarse screening |
| Executable discovery | 1 second | 1 second | Final discovery ranking and promotion eligibility |

Both profiles use the same minute market states, fold boundaries, position sizing,
10 bps fee rate, long/flat constraint, and forced fold-end position close. Each fold
starts with a new account, engine, strategy instance, and position state.

A minute state is knowable at its `ts_event`. In the executable profile, the strategy
receives the state one second later and trades against the BBO available at that time.
Tests verify that it cannot use the quote at the original signal timestamp.

### Data

The executable datasets contain one-second quotes for the five registered discovery
folds and three instruments:

- `BTCUSDT.BINANCE`
- `ETHUSDT.BINANCE`
- `BNBUSDT.BINANCE`

Seven-day folds contain 604,800 quote rows and five-day folds contain 432,000 quote rows.
Each profile-aware manifest records the split, execution profile, quote interval,
execution delay, quote count, source window, and file hashes.

The executable dataset builder accepts discovery windows only. The reranker verifies
that the fast root contains `fast` manifests and the executable root contains
`executable` manifests before running a backtest.

### Method

The offline reranker loaded the ten exported candidates from each smoke run:

- BTC: `smoke-20260830-06`
- ETH: `smoke-20260830-01`
- BNB: `smoke-20260830-01`

For each candidate it ran:

1. five fast discovery folds
2. five executable discovery folds
3. a second set of five executable folds for determinism

This produced 450 fold backtests. The reranker sorted candidates by executable net daily
Sharpe. It also compared return, Sharpe, turnover, exposure, orders, closed positions,
holding duration, and fold return signs.

### Rank stability

| Instrument | Spearman rank correlation | Fast/executable top-3 overlap | Fast champion executable rank | Executable champion fast rank |
|---|---:|---:|---:|---:|
| BTCUSDT | 1.000 | 3/3 | 1 | 1 |
| ETHUSDT | 1.000 | 3/3 | 1 | 1 |
| BNBUSDT | -0.018 | 0/3 | 5 | 7 |

BTC and ETH retained their complete top-ten order. BNB produced an almost unrelated
ordering: the fast champion fell to fifth and the executable champion had ranked seventh
under the fast profile.

The BNB result rules out direct promotion of the fast champion. Execution mismatch can
change candidate selection even when another instrument shows little sensitivity.

### Performance changes

`Sharpe delta` and `return delta` below equal executable minus fast. Return is the mean
net return across five independently funded folds.

| Instrument | Median Sharpe delta | Sharpe delta range | Median return delta |
|---|---:|---:|---:|
| BTCUSDT | +0.005 | -0.014 to +0.116 | +0.0001% |
| ETHUSDT | -0.086 | -0.640 to +0.235 | -0.0156% |
| BNBUSDT | -1.240 | -2.557 to -0.188 | -0.1479% |

BTC candidates changed little. ETH candidates lost a small amount of performance while
retaining their order. Every BNB candidate deteriorated, and the amount of deterioration
varied enough to replace the champion.

### Executable champions

| Instrument | Champion fast rank | Fast net Sharpe | Executable net Sharpe | Fast mean fold return | Executable mean fold return |
|---|---:|---:|---:|---:|---:|
| BTCUSDT | 1 | -6.870 | -6.865 | -0.2932% | -0.2931% |
| ETHUSDT | 1 | -6.360 | -6.446 | -0.3928% | -0.4083% |
| BNBUSDT | 7 | -8.352 | -8.842 | -0.3083% | -0.4098% |

All three executable champions have negative discovery Sharpe and negative mean fold
return. None may proceed to validation.

The smoke runs remain `infrastructure_only`. Increasing them to 300 iterations would
continue search from lineages that have not shown positive discovery evidence.

### Determinism

All 30 candidates reproduced their executable metrics exactly on the second run:

```text
30/30 deterministic
```

This check covered fills, positions, daily returns, and diagnostic aggregates through
exact payload equality. No one-second execution nondeterminism was observed.

### Candidate duplication

Several exported candidates produced identical metrics under both profiles:

- the BTC top three were identical
- the ETH top eight were identical
- several BNB candidates formed identical metric groups

Metric equality does not prove source-code identity, but it shows that top-N capacity can
be occupied by behaviorally equivalent candidates. Candidate deduplication belongs in
Milestone 2 search diagnostics. It does not change the execution-parity conclusion.

### Decision

The registered two-stage discovery protocol is now:

1. OpenEvolve uses the fast profile for candidate generation and coarse screening.
2. The repository reranks a preregistered top-N set with the executable profile.
3. Executable net daily Sharpe determines final discovery rank.
4. The executable evaluation must reproduce exactly on a second run.
5. Promotion gates use executable discovery metrics, not the OpenEvolve fast score.
6. A candidate with non-positive executable discovery Sharpe cannot access validation.

The fast profile remains a compute-saving screen. It is not a promotion-quality
measurement.

### Next step

Milestone 1.3 will measure fee and delay sensitivity on discovery data. The official
profile remains one-second quotes, one-second delay, and 10 bps fees. Alternative fees
and delays are diagnostics and must not become extra ranking objectives.

## Discovery Cost and Delay Sensitivity

### Status

Milestone 1.3 complete. Discovery data only.

No validation or holdout dataset was read. The three smoke-run champions fail discovery
qualification under the registered execution profile.

### Method

Each executable discovery champion ran on one-second quotes under twelve scenarios:

- fees: 0, 5, 10, and 15 bps
- execution delays: 0, 1, and 5 seconds

The official profile remains 10 bps and one second. Alternative scenarios diagnose cost
and delay fragility and do not affect candidate generation or ranking.

Each scenario uses the same five discovery folds, minute states, position sizing, and
strategy code. The 10 bps/one-second scenario must match the executable rerank exactly;
all three instruments passed this consistency check.

### Net Sharpe matrix

| Instrument | Delay | 0 bps | 5 bps | 10 bps | 15 bps |
|---|---:|---:|---:|---:|---:|
| BTCUSDT | 0 sec | 3.467 | -1.428 | -6.870 | -12.540 |
| BTCUSDT | 1 sec | 3.497 | -1.407 | -6.865 | -12.554 |
| BTCUSDT | 5 sec | 3.466 | -1.443 | -6.899 | -12.579 |
| ETHUSDT | 0 sec | 0.858 | -2.827 | -6.360 | -9.659 |
| ETHUSDT | 1 sec | 0.987 | -2.823 | -6.446 | -9.796 |
| ETHUSDT | 5 sec | 0.961 | -2.824 | -6.426 | -9.759 |
| BNBUSDT | 0 sec | -1.252 | -5.124 | -8.352 | -11.006 |
| BNBUSDT | 1 sec | -0.554 | -5.072 | -8.842 | -11.917 |
| BNBUSDT | 5 sec | -0.524 | -5.057 | -8.834 | -11.913 |

### Mean fold net-return matrix

| Instrument | Delay | 0 bps | 5 bps | 10 bps | 15 bps |
|---|---:|---:|---:|---:|---:|
| BTCUSDT | 0 sec | 0.1654% | -0.0639% | -0.2932% | -0.5226% |
| BTCUSDT | 1 sec | 0.1671% | -0.0630% | -0.2931% | -0.5232% |
| BTCUSDT | 5 sec | 0.1655% | -0.0646% | -0.2947% | -0.5248% |
| ETHUSDT | 0 sec | 0.0509% | -0.1709% | -0.3928% | -0.6146% |
| ETHUSDT | 1 sec | 0.0597% | -0.1743% | -0.4083% | -0.6424% |
| ETHUSDT | 5 sec | 0.0586% | -0.1754% | -0.4095% | -0.6435% |
| BNBUSDT | 0 sec | -0.0392% | -0.1737% | -0.3083% | -0.4428% |
| BNBUSDT | 1 sec | -0.0218% | -0.2158% | -0.4098% | -0.6038% |
| BNBUSDT | 5 sec | -0.0206% | -0.2146% | -0.4086% | -0.6025% |

### Findings

#### BTCUSDT

BTC has positive gross performance at zero fees, but turns negative by 5 bps. Delay from
zero to five seconds changes little. The candidate is `cost_fragile`: its edge is too
small for the registered 10 bps model. The additional `delay_sensitive` label records a
small deterioration from one to five seconds while the official result is already
negative.

#### ETHUSDT

ETH also has positive gross performance at zero fees and turns negative by 5 bps. Delay
has little effect relative to fee drag. The candidate is `cost_fragile` and cannot cover
the registered trading cost.

#### BNBUSDT

BNB remains negative even at zero fees under all delays. It is
`economically_rejected`; costs amplify a strategy that lacks positive gross edge.

### Accounting checks

Within each delay, gross behavior and turnover remain fixed while fee drag increases with
the configured instrument fee. Net return declines in line with turnover. Zero-fee runs
report zero fee drag.

The official sensitivity scenario reproduced each executable rerank aggregate
exactly. A mismatch would invalidate the sensitivity report.

### Decision

None of the current smoke champions may access validation:

- BTC: cost-fragile
- ETH: cost-fragile
- BNB: negative before fees

Future candidates must first have positive official executable Sharpe. Cost and delay
labels then act as promotion evidence under the registered protocol in
[`promotion-protocol.md`](../../evolution/docs/promotion-protocol.md).

## Discovery Eligibility Gate Audit

### Status

Milestone 1 discovery-only audit. No validation or holdout data was read.

### Current policy

A candidate must have:

- at least 20 closed positions across discovery
- activity in at least four discovery folds
- no order rejection

Net daily Sharpe remains the only ranking metric after eligibility.

Eligibility evaluation returns structured rejection reasons instead of silently replacing
the score without an audit category.

### Historical checkpoint audit

The three 30-iteration smoke checkpoints contain the following program records:

| Instrument | Programs | Fixed-score rejections | Eligible at 10 trades | 15 trades | 20 trades | 30 trades |
|---|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 23 | 6 | 17 | 17 | 17 | 17 |
| ETHUSDT | 24 | 10 | 14 | 14 | 14 | 14 |
| BNBUSDT | 18 | 4 | 14 | 14 | 14 | 14 |

Changing the historical total-trade threshold from 10 through 30 would not change the
eligible set in these smoke checkpoints. The observed negative results therefore do not
come from a sharp cutoff at 20 trades.

These checkpoints preserve aggregate activity metrics but not fold-level rejection
reasons for every failed evaluation. The audit reports this limitation and does not
infer whether an old fixed-score rejection came from syntax, lifecycle, sandbox, order,
activity, or metric failure.

### Decision

Keep the current 20-position and four-active-fold policy for the next research cycle.
There is no evidence from these checkpoints that lowering the threshold would recover a
lower-turnover candidate. Review the policy again after hypothesis-specific lineages
produce candidates near the threshold.

New evaluations use explicit categories:

- `candidate_validation`
- `lifecycle`
- `sandbox`
- `order_rejection`
- `insufficient_closed_positions`
- `insufficient_active_folds`
- `non_finite_metrics`
- `economic_rejection`

Historical counts remain incomplete where the old artifacts did not preserve the cause.
