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
