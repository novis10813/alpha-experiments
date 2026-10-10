# Experiment Roadmap

Three sequential milestones. Better search is useful only after measurements are
credible, and structural cleanup should support a proven workflow.

| Milestone | Status |
| --- | --- |
| 1. Establish experiment credibility | complete |
| 2. Improve search capability | in progress |
| 3. Strengthen engineering structure | not started |

Current research priorities are in [Current Research Focus](research/current-focus.md).
Standing rules are in [`AGENTS.md`](../AGENTS.md) and the
[repository guide](../AGENTS.md).

## Milestone 1: Establish experiment credibility (complete)

The three OpenEvolve smoke runs (BTC, ETH, BNB, 30 iterations each) remain
`infrastructure_only`. Validation and holdout remain uninspected.

| Item | Outcome | Record |
| --- | --- | --- |
| 1.1 Diagnose the backtest harness | Fixed baselines and a discovery-only diagnostic command. | [Harness diagnostic](../tasks/T05-evolution-credibility/REPORT.md#discovery-harness-diagnostic) |
| 1.2 Align discovery and promotion execution | Fast profile screens candidates. Executable discovery (one-second quotes, one-second delay) sets final rank and must reproduce exactly. | [Execution parity](../tasks/T05-evolution-credibility/REPORT.md#discovery-execution-parity) |
| 1.3 Cost and delay sensitivity | Fees 0/5/10/15 bps, delays 0/1/5 s as diagnostics. BTC and ETH are cost-fragile. BNB is negative before fees. | [Cost and delay sensitivity](../tasks/T05-evolution-credibility/REPORT.md#discovery-cost-and-delay-sensitivity) |
| 1.4 Review eligibility gates | 10 to 30 trade thresholds give identical eligible sets. Rule stays at 20 closed positions and four active folds. | [Eligibility audit](../tasks/T05-evolution-credibility/REPORT.md#discovery-eligibility-gate-audit) |
| 1.5 Discovery promotion gates | Machine-enforced. All smoke runs were rejected before validation loading. | [Promotion protocol](../evolution/docs/promotion-protocol.md) |
| 1.6 Protect validation and holdout | Family IDs, family-level ledger, one-time holdout lock, research statuses. | [Experiment ledger](../evolution/docs/experiment-ledger.md) |

## Milestone 2: Improve search capability

Goal: search several explicit market-structure hypotheses with enough diversity to
find stable rule candidates, without turning OpenEvolve into an unconstrained
strategy generator.

### 2.1 Hypothesis lineages

One falsifiable hypothesis per family, with independent seed strategies and
prompts. Initial families: trend continuation with microstructure confirmation,
down-streak pressure (BTC-focused, BNB separate), and pullback or large-move
exhaustion.

- [ ] A factor note or preregistration note for each lineage
- [ ] A distinct initial program and prompt context for each lineage
- [ ] Independent run IDs, random seeds, and result summaries
- [ ] No claim of cross-instrument generality without explicit evidence

### 2.2 Stateful turnover controls

Let candidates express persistence (separate entry and exit thresholds,
multi-bar confirmation, minimum holds, cooldowns, hysteresis, explicit regime
states) without changing sizing or the long/flat constraint. Turnover is not a
ranking objective. Fees stay in net daily Sharpe.

- [ ] Seed strategies that demonstrate valid state machines
- [ ] Validator and sandbox coverage for mutable-state reset behavior
- [ ] Diagnostics showing whether turnover controls improve gross-to-net conversion

### 2.3 Multiple independent searches

Budget stages: 10 iterations for syntax and lifecycle, 30 for search behavior, 50
to 100 for discovery viability, and 300 only after credible positive discovery
evidence. Prefer several lineages and seeds over one long path.

- [ ] A registered budget policy
- [ ] Multi-seed summaries for each hypothesis family
- [ ] Candidate similarity or rule-structure diagnostics
- [ ] A recorded stop decision for lineages that remain negative

### 2.4 Exploration without restoring rejected lineages

Archive size one with exploitation-only parents protects against OpenEvolve's
fixed-low-score admission but narrows exploration. Try, in order: independent
hypothesis seeds, independent random seeds, diverse inspirations with one eligible
parent lineage, and larger archives only after tests prove rejected candidates
cannot become parents.

- [ ] Tests for parent eligibility and archive admission
- [ ] An experiment comparing independent runs with archive-based diversity
- [ ] A documented exploration policy

### 2.5 Trusted market states

Add normalized states only when a registered hypothesis needs them, with
end-of-bucket timestamps and no future data.

- [ ] A hypothesis reference for every new trusted field
- [ ] Timestamp and no-lookahead tests
- [ ] Distribution and missing-data diagnostics
- [ ] A schema-version migration when fields change

### 2.6 Discovery coverage

Expand discovery to preregistered periods covering different volatility and trend
conditions. Keep folds chronological and validation and holdout unchanged.

- [x] A documented extended discovery calendar ([Market Regime Characterization](../tasks/T07-market-regime/REPORT.md#market-regime-characterization))
- [x] Dataset manifests and hashes for every fold (supplemental audit reports under `outputs/evolution-diagnostics/`)
- [ ] Sharpe uncertainty and concentration diagnostics (bootstrap, day and fold removal)
- [ ] A multiple-testing warning tied to the effective search budget

### Exit criteria

- Each formal run belongs to a documented hypothesis family.
- More than one valid seed lineage exists.
- Strategies can reduce noisy switching through explicit state.
- Executable discovery reranking governs final discovery selection.
- Independent runs provide evidence about convergence and stability.
- Extended discovery covers more than one market regime.
- Iteration budgets increase only after a lineage meets registered viability gates.

## Milestone 3: Strengthen engineering structure

Goal: make every formal experiment reproducible, auditable, and easy to operate
without broad refactoring of working research code.

### 3.1 Immutable run manifests

Write `run_manifest.json` before evaluation: git commit and dirty state, Python,
Nautilus, and OpenEvolve versions, Docker image digest, dataset, config, prompt,
and initial-program hashes, family ID, models, seed, budget, timestamps, and the
parent checkpoint on resume. Resume verifies immutable fields.

- [ ] Run-manifest creation and verification
- [ ] Resume rejection for incompatible manifests
- [ ] Tests for hashes, versions, and dirty-tree behavior

### 3.2 Durable experiment ledger

A repository-level ledger of formal experiments: family ID, instrument, run IDs,
commit, dataset and config identity, discovery conclusion, validation and holdout
use, final status, and a link to the research note.

- [ ] A documented ledger format
- [ ] One entry for the current smoke framework marked `infrastructure_only`
- [ ] A command or helper that validates ledger and run-manifest consistency

### 3.3 Separate CLI responsibilities

`build-data`, `diagnose`, `evolve`, `rerank`, `validate`, and `promote` each get
only the splits they need, enforced in code.

- [ ] Documented commands and examples
- [ ] Tests proving each command can access only its allowed splits
- [ ] Clear resume and failure-recovery output

### 3.4 Organize tests by responsibility

Unit, contract, sandbox, Nautilus integration, optional catalog integration, and
research regression groups. Unit tests need no S3, MinIO, LLM endpoint, or Docker
network.

- [ ] Documented test groups and commands
- [ ] Stable fixtures for execution and metric regressions
- [ ] Optional integration tests skipped cleanly when dependencies are unavailable

### 3.5 Repository preflight

One command that checks tests, credentials, staged artifacts (`.env`, `data/`,
checkpoints, outputs), split overlap, dataset schema and hashes, image and lock
currency, and treats prompt diff markers as intentional content.

- [ ] A single local preflight command
- [ ] Tests for secret and generated-artifact exclusions
- [ ] Documentation for expected warnings and intentional exceptions

### 3.6 Consolidate only proven duplication

Extract shared report code only when several active reports use the same
behavior. No broad report framework.

- [ ] A small inventory of repeated code before each refactor
- [ ] Regression tests that preserve report outputs
- [ ] No unrelated formatting or abstraction churn

### Exit criteria

- A clean checkout can reproduce a formal run from its manifest and local data.
- Every formal experiment appears in the ledger.
- CLI commands enforce discovery, validation, and holdout boundaries.
- Resume detects incompatible code, configuration, prompts, images, or datasets.
- Test groups separate local unit coverage from optional infrastructure integration.
- One preflight command catches credentials, generated artifacts, split errors, and failed tests.
