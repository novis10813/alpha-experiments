# Evolution Promotion Protocol

## Purpose

This protocol controls when an evolved strategy may access validation and holdout data.
Discovery metrics, executable reranking, and sensitivity diagnostics must qualify a
candidate before the validator opens a validation manifest.

## Discovery qualification

The executable discovery champion must satisfy all of the following:

- net daily Sharpe is positive
- median fold net return is positive
- at least four discovery folds contain a closed position
- at least three of five fold net returns are positive
- the executable rerun reproduces exactly
- sensitivity results belong to the same candidate
- the candidate is not labelled `cost_fragile` or `delay_fragile`
- the run supplies a registered research-family ID and immutable hypothesis

A failed gate writes `promotion-disqualified.json`. It does not load validation or
holdout data.

## Registered execution and sensitivity

Final discovery rank uses one-second quotes, a one-second delay, and 10 bps fees. The
sensitivity matrix uses discovery data only:

- fees: 0, 5, 10, and 15 bps
- delays: 0, 1, and 5 seconds

Alternative scenarios are diagnostics. They do not become ranking objectives and must
not feed candidate generation.

## Validation

Validation evaluates the preregistered candidate set twice and removes candidates whose
results do not reproduce. Net daily Sharpe selects one validation champion.

Validation results must not modify the hypothesis, candidate code, discovery ranking,
fee assumptions, delay assumptions, or promotion gates.

## Holdout

The validator acquires a family-and-instrument holdout lock before loading holdout data.
The lock is independent of run ID. Starting another run under the same family cannot
reset holdout access.

Only the validation champion may consume holdout, once. Holdout results cannot return to
OpenEvolve prompts, evaluator feedback, feature definitions, or search configuration.

## Research statuses

| Status | Meaning |
|---|---|
| `infrastructure_only` | The run exercised infrastructure but failed discovery qualification. |
| `rejected` | Available evidence rejects the strategy or hypothesis under registered assumptions. |
| `inconclusive` | Required evaluation is missing or the evidence cannot support a decision. |
| `feature_candidate` | Diagnostics support use as a feature, filter, state, or execution input; this status requires a separate factor note. |
| `rule_candidate` | Validation and holdout are both positive, but the full alpha acceptance criteria are not met. |
| `accepted_alpha` | The candidate passes the preregistered feasibility and baseline criteria. |

A positive result in one evaluation window does not create a feature or rule candidate.

## CLI

Formal promotion requires governance metadata:

```bash
uv run python -m evolution promote \
  --instrument-id BTCUSDT.BINANCE \
  --run-id trend-flow-run-1 \
  --family-id trend-flow-confirmation-v1 \
  --hypothesis "Price continuation survives costs when trend and signed flow agree"
```

The local family ledger and holdout locks live under `.local/evolution-governance/` by
default and must remain outside Git.
