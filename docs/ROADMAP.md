# Experiment Roadmap

This roadmap organizes repository work into three sequential milestones:

1. establish experiment credibility
2. improve search capability
3. strengthen engineering structure

Complete the milestones in order. Better search is useful only after the backtest and
selection protocol produce credible measurements. Structural cleanup should support a
proven workflow rather than define one prematurely.

## Current baseline

The OpenEvolve smoke run completed 30 iterations independently for BTCUSDT, ETHUSDT,
and BNBUSDT. All runs produced checkpoints and ten eligible discovery candidates, and
all 107 tests passed. The best discovery Sharpe ratio for each instrument remained
negative.

These runs prove that the infrastructure executes end to end. They do not provide alpha
evidence. Validation and holdout results remain uninspected and must stay untouched
until a candidate passes the discovery gates defined in this roadmap.

The canonical record of the current run is
[`research/openevolve-strategy-evolution.md`](research/openevolve-strategy-evolution.md).

---

# Milestone 1: Establish experiment credibility

## Goal

Make discovery fitness, execution assumptions, data splits, and promotion rules strong
enough that a better score represents a better research candidate rather than a backtest
artifact.

Do not resume the current searches to 300 iterations until this milestone is complete.

## 1.1 Diagnose the current backtest harness

Add a discovery-only diagnostic that evaluates the initial strategy, SMA 3/8,
buy-and-hold, and selected discovery candidates with the same reporting schema.

Report at least:

- gross return
- fee drag
- net return
- gross and net daily Sharpe ratio
- closed positions and order count
- turnover
- exposure ratio
- average and median holding duration
- average gross PnL and fee per closed position
- per-fold returns and Sharpe ratios
- best-day and worst-day contribution

The first question to answer is whether candidates lose money before fees or whether a
small gross edge is consumed by turnover and execution costs.

### Deliverables

- [ ] A reproducible discovery diagnostic command
- [ ] Unit tests for all new metric calculations
- [ ] A research note recording the diagnosis for the current smoke runs
- [ ] No reads from validation or holdout datasets

## 1.2 Align discovery and promotion execution

Discovery currently uses coarse quotes and zero execution delay, while validation and
holdout use one-second quotes and a one-second delay. Measure the effect of this mismatch
on discovery data.

Use a two-stage discovery evaluation:

1. a coarse screen rejects invalid or clearly poor candidates cheaply
2. an executable rerank evaluates surviving candidates with discovery-period quote data
   and the same delay assumptions used during promotion

Keep validation and holdout physically and logically isolated from both stages.

### Deliverables

- [ ] A coarse-versus-executable comparison on discovery data
- [ ] A documented execution model used consistently for final discovery ranking and promotion
- [ ] Tests covering quote ordering, signal availability, delay, fees, and end-of-window positions
- [ ] Deterministic reruns that reproduce metrics exactly

## 1.3 Add cost and delay sensitivity

Run diagnostic scenarios on discovery data without changing the official fitness:

- fees of 0, 5, 10, and 15 bps
- execution delays of 0, 1, and 5 seconds where data permits

The official ranking metric remains the annualized Sharpe ratio of after-fee daily
returns under the registered execution assumptions. Sensitivity results act as
qualification evidence, not ranking inputs.

### Deliverables

- [ ] A standard fee-and-delay sensitivity table
- [ ] A clear distinction between official fitness and diagnostic scenarios
- [ ] A recorded reason when an apparent edge exists only under unrealistic costs

## 1.4 Review eligibility gates

Measure how the current requirements of 20 closed positions and four active folds affect
candidate selection. In particular, check whether the trade-count gate rejects lower
turnover candidates and encourages fee-heavy switching.

Compare discovery eligibility under several trade-count thresholds before changing the
official rule. If the rule changes, preserve cross-fold activity and register the new
rule before the next search.

### Deliverables

- [ ] Sensitivity analysis for minimum closed-position thresholds
- [ ] Counts of candidates rejected for each eligibility reason
- [ ] Explicit rejection categories for syntax, lifecycle, sandbox, order, activity, and metric failures
- [ ] A documented final eligibility rule

## 1.5 Define discovery promotion gates

A run may inspect validation only when its discovery candidate satisfies a preregistered
set of conditions. Candidate ranking still uses only official net daily Sharpe.

The initial promotion gate should require:

- positive discovery net Sharpe
- positive median fold return
- activity across at least four discovery folds
- positive returns in a majority of discovery folds
- deterministic rerun agreement
- survival under executable discovery reranking
- no catastrophic collapse under the registered cost and delay sensitivity checks
- a documented market-structure hypothesis

Thresholds must be fixed before the next qualifying search. A negative discovery
champion must not consume validation merely because a run reached its iteration target.

### Deliverables

- [ ] Machine-enforced discovery promotion gates
- [ ] Tests showing that failing candidates cannot access validation
- [ ] A preregistered promotion protocol in the research documentation

## 1.6 Protect validation and holdout

Keep the following roles fixed:

- discovery supports repeated search and diagnosis
- validation selects one champion from a preregistered candidate set
- holdout evaluates that validation champion once

Track holdout use at the hypothesis-family level, not only the run level. Starting a new
run ID must not reset the research family's holdout status.

Use more precise research statuses:

- `infrastructure_only`
- `rejected`
- `inconclusive`
- `feature_candidate`
- `rule_candidate`
- `accepted_alpha`

A positive return in one window alone is not enough for `feature_candidate` status.

### Deliverables

- [ ] A hypothesis-family identifier for every formal evolution run
- [ ] A family-level validation and holdout ledger
- [ ] A one-time holdout lock enforced by code
- [ ] Documented definitions for all research statuses

## Milestone 1 exit criteria

Milestone 1 is complete when:

- discovery ranking uses an execution model representative of promotion
- gross, fee, and net performance can be separated
- cost and delay sensitivity is reproducible
- eligibility and promotion failures have explicit reasons
- code prevents an unqualified run from reading validation or holdout
- repeated evaluation of the same candidate produces identical results
- the research protocol states when validation and holdout may be consumed

---

# Milestone 2: Improve search capability

## Goal

Search several explicit market-structure hypotheses with enough diversity to find
stable rule candidates without turning OpenEvolve into an unconstrained strategy
generator.

Begin this milestone only after Milestone 1 exit criteria are met.

## 2.1 Replace the single-seed search with hypothesis lineages

Create independent seed strategies and prompts for a small set of research families.
Each family should express one falsifiable hypothesis and define the role of each input.
Do not combine unrelated hypotheses in one evolution run.

Initial families:

### Trend continuation with microstructure confirmation

Test whether medium-horizon upward price state predicts continuation only when signed
trade flow and order book pressure agree. Spread and volatility may act as entry filters.

### Down-streak pressure

Extend the existing BTC-focused research with volatility, trade-density, signed-volume,
and broad-trend gates. Treat BNB separately and do not require a universal three-asset
rule.

### Pullback and large-move exhaustion

Test whether a long/flat strategy improves entry and exit timing by waiting for pullback
completion or exiting when flow and order book confirmation weaken after a large move.

### Deliverables

- [ ] A factor note or preregistration note for each lineage
- [ ] A distinct initial program and prompt context for each lineage
- [ ] Independent run IDs, random seeds, and result summaries
- [ ] No claim of cross-instrument generality without explicit evidence

## 2.2 Give strategies stateful turnover controls

Let candidates express trading persistence without changing position sizing or the
long/flat constraint. Useful mechanisms include:

- separate entry and exit thresholds
- entry confirmation over multiple completed bars
- minimum holding periods
- cooldown after exit
- hysteresis around noisy thresholds
- regime transitions represented as explicit states

These controls belong to the strategy search space. Turnover does not become a separate
ranking objective; fees remain reflected in net daily Sharpe.

### Deliverables

- [ ] Seed strategies that demonstrate valid state machines
- [ ] Validator and sandbox coverage for mutable-state reset behavior
- [ ] Diagnostics showing whether turnover controls improve gross-to-net conversion

## 2.3 Run multiple independent searches

Use multiple short and medium runs before allocating a large iteration budget. Prefer
several independent lineages and random seeds over one 300-iteration path from a single
MA seed.

Suggested budget stages:

1. 10 iterations for syntax and lifecycle checks
2. 30 iterations for search-behavior smoke tests
3. 50 to 100 iterations for discovery viability
4. 300 iterations only after a lineage produces credible positive discovery evidence

Compare whether independent runs converge on similar states and parameter ranges.

### Deliverables

- [ ] A registered budget policy
- [ ] Multi-seed summaries for each hypothesis family
- [ ] Candidate similarity or rule-structure diagnostics
- [ ] A recorded stop decision for lineages that remain negative

## 2.4 Improve exploration without restoring rejected lineages

The current archive size of one and exploitation-only parent sampling protect the search
from OpenEvolve's fixed-low-score admission behavior, but they also narrow exploration.

Test safer diversity mechanisms in this order:

1. multiple independent runs from different hypothesis seeds
2. independent random seeds within one hypothesis family
3. diverse inspiration candidates while retaining one eligible parent lineage
4. larger parent archives only after tests prove rejected candidates cannot become parents

Do not change archive behavior without regression tests for syntax failures, lifecycle
failures, and fixed rejected scores.

### Deliverables

- [ ] Tests for parent eligibility and archive admission
- [ ] An experiment comparing independent runs with archive-based diversity
- [ ] A documented exploration policy

## 2.5 Improve trusted market states selectively

Add normalized states only when a registered hypothesis needs them. Candidate strategies
may use:

- returns over fixed completed-bar horizons
- realized volatility or normalized range
- close location within the completed bar
- volume and trade density relative to trailing baselines
- changes and persistence in signed flow or order book imbalance
- spread relative to its trailing baseline

Calculate trusted features with end-of-bucket timestamps and no future data. Avoid turning
`EvolutionMarketState` into an unreviewed feature dump.

### Deliverables

- [ ] A hypothesis reference for every new trusted field
- [ ] Timestamp and no-lookahead tests
- [ ] Distribution and missing-data diagnostics
- [ ] A schema-version migration when fields change

## 2.6 Expand discovery coverage

Daily Sharpe estimated from roughly one month has high uncertainty. Expand discovery to
multiple preregistered periods representing different volatility and trend conditions.
Keep all folds chronological and keep validation and holdout unchanged until a new data
protocol is registered.

Report:

- fold-level stability
- bootstrap uncertainty for Sharpe
- concentration in individual days
- sensitivity to removing one day or one fold
- number of evaluated and unique candidates

Official ranking may remain net daily Sharpe. Statistical uncertainty and search-budget
information belong in diagnostics and promotion gates.

### Deliverables

- [ ] A documented extended discovery calendar
- [ ] Dataset manifests and hashes for every fold
- [ ] Sharpe uncertainty and concentration diagnostics
- [ ] A multiple-testing warning tied to the effective search budget

## Milestone 2 exit criteria

Milestone 2 is complete when:

- each formal run belongs to a documented hypothesis family
- the repository contains more than one valid seed lineage
- strategies can reduce noisy switching through explicit state
- executable discovery reranking governs final discovery selection
- independent runs provide evidence about convergence and stability
- extended discovery covers more than one market regime
- iteration budgets increase only after a lineage meets registered viability gates

---

# Milestone 3: Strengthen engineering structure

## Goal

Make every formal experiment reproducible, auditable, and easy to operate without broad
refactoring of working research code.

Engineering work in this milestone should preserve the protocol established in the first
two milestones.

## 3.1 Add immutable run manifests

Every evolution run should write a `run_manifest.json` before evaluation begins. Record:

- git commit and dirty-tree state
- Python, Nautilus Trader, and OpenEvolve versions
- Docker image tag and digest
- dataset manifest hashes
- config, prompt, and initial-program hashes
- instrument and hypothesis-family ID
- model names and weights
- random seed and iteration budget
- start and completion timestamps
- parent run and checkpoint when resumed

Resume must verify immutable fields rather than silently accepting a changed environment.

### Deliverables

- [ ] Run-manifest creation and verification
- [ ] Resume rejection for incompatible manifests
- [ ] Tests for hashes, versions, and dirty-tree behavior

## 3.2 Add a durable experiment ledger

Create a repository-level ledger that records formal experiments without committing large
checkpoints or generated datasets. Each entry should include:

- hypothesis-family ID
- instrument
- run IDs
- code commit
- dataset and config identity
- discovery conclusion
- whether validation was inspected
- whether holdout was consumed
- final research status
- links to the durable research note

The ledger should make accidental reuse of consumed holdout data visible during review.

### Deliverables

- [ ] A documented ledger format
- [ ] One entry for the current smoke framework marked `infrastructure_only`
- [ ] A command or helper that validates ledger and run-manifest consistency

## 3.3 Separate CLI responsibilities

Expose commands with narrow data access:

- `build-data` prepares registered local datasets
- `diagnose` reads discovery only
- `evolve` reads discovery only
- `rerank` performs executable discovery reranking
- `validate` evaluates a preregistered candidate set
- `promote` consumes holdout for the validation champion

Enforce the boundary in code rather than relying on command-line discipline.

### Deliverables

- [ ] Documented commands and examples
- [ ] Tests proving each command can access only its allowed splits
- [ ] Clear resume and failure-recovery output

## 3.4 Organize tests by responsibility

Keep `unittest` and separate tests conceptually into:

- unit tests for metrics, candidate checks, and state construction
- contract tests for prompts, configuration, manifests, and split rules
- sandbox tests for isolation and resource restrictions
- integration tests for Nautilus backtests
- optional catalog integration tests that require local credentials
- research regression tests using small fixed fixtures

Unit tests must not require S3, MinIO, OpenRouter, or the Docker network.

### Deliverables

- [ ] Documented test groups and commands
- [ ] Stable fixtures for execution and metric regressions
- [ ] Optional integration tests skipped cleanly when dependencies are unavailable

## 3.5 Add repository preflight checks

Before a formal run or commit, check:

- the unit test suite passes
- tracked files contain no credentials
- `.env`, `.local/`, checkpoints, and generated outputs are not staged
- data splits do not overlap
- dataset schema versions and hashes match
- the Docker image and dependency lock are current
- prompt diff markers are treated as intentional content, not unresolved Git conflicts

### Deliverables

- [ ] A single local preflight command
- [ ] Tests for secret and generated-artifact exclusions
- [ ] Documentation for expected warnings and intentional exceptions

## 3.6 Consolidate only proven duplication

Keep focused research reports separate. Extract shared code only when several active
reports use the same behavior, such as:

- fold summaries
- cost sensitivity tables
- event de-overlap
- manifest metadata
- deterministic CSV and Markdown output

Avoid a broad report framework or configuration system unless concrete duplication makes
current experiments harder to verify.

### Deliverables

- [ ] A small inventory of repeated code before each refactor
- [ ] Regression tests that preserve report outputs
- [ ] No unrelated formatting or abstraction churn

## Milestone 3 exit criteria

Milestone 3 is complete when:

- a clean checkout can reproduce a formal run from its manifest and documented local data
- every formal experiment appears in the ledger
- CLI commands enforce discovery, validation, and holdout boundaries
- resume detects incompatible code, configuration, prompts, images, or datasets
- test groups separate local unit coverage from optional infrastructure integration
- one preflight command catches credentials, generated artifacts, split errors, and failed tests

---

# Global constraints

These rules apply throughout the roadmap:

- Keep the canonical alpha row limited to `ts_event`, `instrument_id`, `alpha_name`, and `value`.
- Timestamp completed aggregation states at the end of the interval.
- Keep prices, forward returns, thresholds, positions, fills, PnL, and drawdown in diagnostics or backtests.
- Use Nautilus Trader objects and APIs for market data and simulation.
- Read the finished catalog; do not trigger catalog conversion or write to S3.
- Keep credentials outside tracked files.
- Treat instrument-specific evidence as instrument-specific.
- Do not inspect holdout to decide how to change a hypothesis, feature, fitness rule, or search configuration.
- Record rejected and inconclusive experiments. A negative result is part of the research history.

# Immediate next step

Start Milestone 1 with the discovery harness diagnostic. Do not increase the current
OpenEvolve iteration budget or inspect validation and holdout until the diagnostic,
execution alignment, and promotion gates are complete.
