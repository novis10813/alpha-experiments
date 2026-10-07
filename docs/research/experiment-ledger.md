# Evolution Experiment Ledger

Formal evolution runs use a local machine-enforced ledger under:

```text
.local/evolution-governance/<family-id>/ledger.json
```

The ledger stays local because it records operational validation and holdout access. A
durable research note should summarize the final status without copying validation or
holdout metrics into prompts or search inputs.

## Family identity

A family ID names one hypothesis lineage, not one process invocation. Use lowercase
letters, digits, and hyphens, for example:

```text
trend-flow-confirmation-v1
down-streak-pressure-btc-v1
large-move-exhaustion-v1
```

Register one immutable hypothesis string for the family. New random seeds and run IDs
belong to the same family when they test the same hypothesis and search space.

## Recorded fields

The machine ledger records:

- family ID
- immutable hypothesis
- instrument IDs
- run IDs
- whether validation has been consumed
- validation run ID
- whether holdout has been consumed
- holdout run and candidate IDs

A family-level holdout lock uses exclusive file creation before holdout loading. A new
run ID cannot bypass an existing lock.

## Smoke-run classification

The current BTC, ETH, and BNB smoke runs are `infrastructure_only`:

- all executable discovery champions have negative Sharpe
- all fail the discovery qualification gate
- validation remains uninspected
- holdout remains unconsumed

They do not require ledger registration because they predate the family-ID protocol and
cannot pass the discovery gate. Future formal runs must register before promotion.

## Observation studies

Discovery-only observation studies are recorded here so that their trial counts
count against any hypothesis derived from them. They are not evolution families
and have no machine ledger entry. None of them read validation or holdout data.

Common inputs: BTC, ETH, and BNB discovery folds 1-5 (2026-06-13 to 2026-07-12,
2026-07-01 missing) and the supplemental discovery splits (2026-08-29 to
2026-09-20), 51 days per instrument. Cost is the v1 spot profile (10 bps per fill)
unless stated. Mid-price returns, bid/ask fills in A3.

Reproduce from the repository root with local discovery data under `.local/`.
Run in this order, because later steps read earlier outputs:

```bash
uv run python -m reports.observe_a1_large_moves      # A1 -> outputs/observe-a1/
uv run python -m reports.observe_a2_precursors       # A2 -> outputs/observe-a2/
uv run python -m reports.observe_a2_conditional      # A2 conditional breakeven (stdout)
uv run python -m reports.observe_f9_fold4            # F9 (stdout)
uv run python -m reports.observe_a3_triple_barrier   # A3 -> outputs/observe-a3/
uv run python -m reports.observe_a3_recost           # A1 and A3 under draft v2 fees (stdout)
```

Each script's docstring records its preregistered definitions and pass rules.

| ID | Date | Question | Trials | Result | Status |
| --- | --- | --- | --- | --- | --- |
| A1 | 2026-10-07 | At which horizons do moves exceed round-trip cost? | 21 descriptive cells (3 instruments x 7 horizons) | Breakeven hit rate is above 1.0 at 1-15 min, 0.90-1.03 at 30 min, 0.64-0.69 at 240 min. Large moves are direction-symmetric. | descriptive |
| A2 | 2026-10-07 | Which trailing features precede 240 min direction and 30/60 min large moves? | 93 screened (27 direction, 66 magnitude), plus descriptive stratified, hourly, and conditional tables | Only 240 min reversal passed the preregistered screen (BTC, ETH). Volatility clustering and the UTC 13-15 window predict large moves on all instruments. | screen only |
| F9 | 2026-10-07 | Why does the 240 min reversal flip sign in discovery_4? | 12 screened (4 state variables x 3 instruments) | The flip comes from a multi-day uptrend, not intraday failure. Only trailing 24h move size passed the screen. | descriptive |
| A3 | 2026-10-07 | Does the 4h reversal after a large 24h move survive triple-barrier execution? | 48 configs (3 instruments x 2 conditions x 4 barriers x 2 entry delays), plus 72 re-costed cells under the draft v2 profile | Gross 0-7 bps per trade against 20 bps cost. All 48 configs are net negative. Under v2 taker fees, BTC and ETH lose 4-11 bps per trade. | `rejected` |

Method note from A2 and A3: minute-pooled decile spreads overstated per-trade
gross edge by 2-5x compared with non-overlapping first-trigger trades. Treat
minute-level IC and decile tables as screening evidence only.

Cost profile context: [Execution Cost Profile v2](execution-cost-profile-v2.md).
