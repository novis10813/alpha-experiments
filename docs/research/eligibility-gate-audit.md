# Discovery Eligibility Gate Audit

## Status

Milestone 1 discovery-only audit. No validation or holdout data was read.

## Current policy

A candidate must have:

- at least 20 closed positions across discovery
- activity in at least four discovery folds
- no order rejection

Net daily Sharpe remains the only ranking metric after eligibility.

The policy now lives in `evolution/eligibility.py`. Eligibility evaluation returns
structured rejection reasons instead of silently replacing the score without an audit
category.

## Historical checkpoint audit

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

## Decision

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
