# OpenEvolve Long/Flat Strategy Evolution

## Research status

This framework is research infrastructure, not evidence that any evolved strategy is
an alpha. It runs independent BTCUSDT, ETHUSDT, and BNBUSDT searches over discovery
data, ranks the discovery archive on an unseen validation window, and evaluates only
the validation winner once on the final holdout. Holdout results must never be fed
back into OpenEvolve.

The editable program is a Nautilus Trader `Strategy`. Trusted code fixes the CASH
account, 100,000 USDT starting balance, approximately 10,000 USDT long position,
market IOC execution, 10 bps maker/taker fees, long/flat constraint, data splits,
scoring, and promotion gates. Candidate execution occurs in a separate Docker
container with no network, a read-only root filesystem and dataset, one CPU, 1 GiB
RAM, a PID limit, no Linux capabilities, and `no-new-privileges`.

## Data and timestamp semantics

The live catalog coverage audit on 2026-08-29 found common BTC/ETH/BNB data for
2026-06-13 through 2026-06-30 and 2026-07-02 through 2026-07-24, with 2026-07-01
missing. The executable split was therefore adjusted to discovery 2026-06-13 through
2026-07-12, validation 2026-07-12 through 2026-07-18, and holdout 2026-07-18 through
2026-07-25. The isolated 2026-08-28 day is quarantined and unused.

On 2026-09-21 supplemental executable-profile discovery data was added under
`.local/evolution-data-supplemental/`: BTCUSDT 2026-09-05 through 2026-09-21,
ETHUSDT and BNBUSDT 2026-08-29 through 2026-09-21 (continuing BTC's existing
2026-08-29 through 2026-09-05 supplements). All three splits passed the
supplemental coverage audit with zero missing state buckets or quote seconds.
These are isolated discovery-only supplements; they are not registered
evaluator folds and do not touch the protected validation/holdout windows. This replaces the
original August validation/holdout proposal, which had no continuous catalog data.

Build local data with:

```bash
uv run python -m evolution build-data --instrument-id BTCUSDT.BINANCE
```

The builder reads the finished S3 Nautilus catalog one closed UTC day at a time and
writes only to `.local/evolution-data/`. `EvolutionMarketState.ts_event` is the end of
the complete one-minute bucket. Its `ts_init` sorts after same-time quote/bar inputs.
Discovery, validation, and holdout are physically separate and each manifest records
schema version, source bounds, row/gap counts, and file hashes.

## Evolution commands

Build the sandbox image, then run a 30-iteration smoke:

```bash
docker build -f evolution/docker/Dockerfile -t alpha-evolution-sandbox:0.2 .
export EVOLUTION_SANDBOX_IMAGE=alpha-evolution-sandbox:0.2
uv run python -m evolution evolve --instrument-id BTCUSDT.BINANCE --run-id smoke-001 --iterations 30
```

The LLM endpoint, model, and key handling are described in the
[repository guide](../repository-guide.md#configuration). `--iterations` is a total
target. On failure the runner preserves checkpoints and prints a resume command,
and `resume` defaults to the last approved target. Iteration budgets follow
[ROADMAP 2.3](../ROADMAP.md#23-multiple-independent-searches).

OpenEvolve 0.3.2 admits fixed-low-score programs while an archive still has empty
slots. The parent archive is therefore intentionally size one with exploitation-only
parent sampling: only the current best eligible program can be a parent. MAP-Elites
cells still retain diverse programs and can supply inspiration, without allowing a
rejected syntax or lifecycle candidate to poison the lineage. Promotion ranking is
separate: it considers every checkpoint program that passed evaluation, not only the
single parent archive slot.

The configured single outer retry is deliberately bounded because OpenEvolve's
retry count also configures the OpenAI client's inner retries. Malformed diffs,
empty responses, and non-transient provider errors remain failed iterations;
checkpoint and resume is the recovery path.

## Promotion rule

Discovery fitness is only the annualized Sharpe ratio of after-fee daily portfolio
returns, using 365-day annualization, zero risk-free rate, and sample volatility. Daily
equity includes cash plus any long inventory marked at the best bid. Candidates still
need at least 20 closed positions and four active folds as evaluation eligibility gates.
The top 10 discovery candidates enter validation. A champion is feasible only when
validation and holdout returns are positive, both beat SMA 3/8 Sharpe, both have
drawdown no worse than buy-and-hold, each has at least three closed positions, and a
deterministic rerun matches. Otherwise the durable conclusion is `rejected` or
`feature_candidate`, never a forced alpha claim.

## 30-iteration smoke results (2026-08-30)

All three independent discovery runs exited successfully, produced checkpoint 30,
and exported ten eligible candidates. The best discovery results were:

| Instrument | Run ID | Sharpe | Median fold return | Worst fold return | Closed positions |
| --- | --- | ---: | ---: | ---: | ---: |
| BTCUSDT.BINANCE | `smoke-20260830-06` | -6.8703 | -0.3257% | -0.7824% | 115 |
| ETHUSDT.BINANCE | `smoke-20260830-01` | -6.3601 | -0.5012% | -0.7179% | 117 |
| BNBUSDT.BINANCE | `smoke-20260830-01` | -7.0697 | -0.2827% | -0.4168% | 104 |

These are negative discovery results, not alpha evidence. Validation and holdout were
not inspected during the smoke phase. The runs are classified `infrastructure_only`
in the [experiment ledger](experiment-ledger.md#smoke-run-classification).
