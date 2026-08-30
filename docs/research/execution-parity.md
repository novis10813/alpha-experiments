# Discovery Execution Parity

## Status

Milestone 1.2 complete. Discovery data only.

This analysis did not read validation or holdout datasets and did not inspect validation
or holdout results. None of the evaluated candidates qualifies for validation.

## Question

The OpenEvolve search used 60-second quotes with zero execution delay. Promotion uses
one-second quotes with a one-second delay. This analysis tests whether the faster
discovery model changes candidate performance or ranking when applied to the same five
discovery folds.

## Registered execution profiles

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

## Data

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

## Method

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

## Rank stability

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

## Performance changes

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

## Executable champions

| Instrument | Champion fast rank | Fast net Sharpe | Executable net Sharpe | Fast mean fold return | Executable mean fold return |
|---|---:|---:|---:|---:|---:|
| BTCUSDT | 1 | -6.870 | -6.865 | -0.2932% | -0.2931% |
| ETHUSDT | 1 | -6.360 | -6.446 | -0.3928% | -0.4083% |
| BNBUSDT | 7 | -8.352 | -8.842 | -0.3083% | -0.4098% |

All three executable champions have negative discovery Sharpe and negative mean fold
return. None may proceed to validation.

The smoke runs remain `infrastructure_only`. Increasing them to 300 iterations would
continue search from lineages that have not shown positive discovery evidence.

## Determinism

All 30 candidates reproduced their executable metrics exactly on the second run:

```text
30/30 deterministic
```

This check covered fills, positions, daily returns, and diagnostic aggregates through
exact payload equality. No one-second execution nondeterminism was observed.

## Candidate duplication

Several exported candidates produced identical metrics under both profiles:

- the BTC top three were identical
- the ETH top eight were identical
- several BNB candidates formed identical metric groups

Metric equality does not prove source-code identity, but it shows that top-N capacity can
be occupied by behaviorally equivalent candidates. Candidate deduplication belongs in
Milestone 2 search diagnostics. It does not change the execution-parity conclusion.

## Decision

The registered two-stage discovery protocol is now:

1. OpenEvolve uses the fast profile for candidate generation and coarse screening.
2. The repository reranks a preregistered top-N set with the executable profile.
3. Executable net daily Sharpe determines final discovery rank.
4. The executable evaluation must reproduce exactly on a second run.
5. Promotion gates use executable discovery metrics, not the OpenEvolve fast score.
6. A candidate with non-positive executable discovery Sharpe cannot access validation.

The fast profile remains a compute-saving screen. It is not a promotion-quality
measurement.

## Commands

Build one-second discovery data:

```bash
uv run python -m evolution build-executable-discovery \
  --instrument-id BTCUSDT.BINANCE
```

Rerank exported candidates:

```bash
uv run python -m evolution rerank \
  --instrument-id BTCUSDT.BINANCE \
  --run-id smoke-20260830-06 \
  --top-n 10
```

Generated `rerank.json` files remain under `outputs/evolution/`. They are local artifacts;
this note is the durable research record.

## Next step

Milestone 1.3 will measure fee and delay sensitivity on discovery data. The official
profile remains one-second quotes, one-second delay, and 10 bps fees. Alternative fees
and delays are diagnostics and must not become extra ranking objectives.
