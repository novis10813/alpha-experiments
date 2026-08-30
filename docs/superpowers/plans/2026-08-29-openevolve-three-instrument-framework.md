# OpenEvolve Three-Instrument Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a secure, reproducible OpenEvolve framework that evolves and promotes independent long/flat Nautilus Trader strategies for BTCUSDT, ETHUSDT, and BNBUSDT.

**Architecture:** Trusted modules build timestamp-safe local datasets, validate candidate source, execute candidates inside a locked-down Docker container, calculate immutable multi-fold fitness, and promote archive candidates through validation and a once-only holdout. OpenEvolve only edits the marked body of an initial Nautilus `Strategy`; orchestration, data, scoring, safety policy, and reporting remain outside the evolve block.

**Tech Stack:** Python 3.13, Nautilus Trader 1.228+, OpenEvolve 0.3.2, PyArrow/Parquet, Docker, `unittest`, `uv`.

---

### Task 1: Immutable experiment specification and instruments

**Files:**
- Create: `evolution/spec.py`
- Create: `evolution/instruments.py`
- Test: `tests/test_evolution_spec.py`

- [ ] **Step 1: Write failing tests** for exact discovery/validation/holdout boundaries, five non-overlapping folds, per-symbol precision, 0.001 fees, CASH-compatible currencies, and isolated output paths.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_evolution_spec` and verify imports fail.
- [ ] **Step 3: Implement** frozen split/instrument specs plus `CurrencyPair` factories for BTC/ETH/BNB with price precision 2 and size precisions 5/4/3.
- [ ] **Step 4: Run** the focused test and verify it passes.

### Task 2: Timestamp-safe market-state dataset

**Files:**
- Create: `evolution/market_state.py`
- Create: `evolution/dataset.py`
- Test: `tests/test_evolution_dataset.py`

- [ ] **Step 1: Write failing tests** using fake trades/depths for minute-end timestamps, global tick-rule continuity across UTC days, OHLC/activity/imbalance/Depth10/BBO fields, gaps, hashes, and physical split separation.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_evolution_dataset` and verify failure.
- [ ] **Step 3: Implement** `EvolutionMarketState` with Nautilus custom-data JSON/Arrow callbacks, deterministic aggregation, one-day-at-a-time read-only catalog queries, local Parquet writes, and a schema-versioned manifest containing source bounds, row counts, gaps, and SHA-256 hashes.
- [ ] **Step 4: Ensure** state `ts_event` is bucket end and `ts_init` is later than same-time quote/bar inputs; never read credentials into manifests or logs.
- [ ] **Step 5: Run** the focused test and verify it passes.

### Task 3: Candidate contract and static safety policy

**Files:**
- Create: `evolution/candidate.py`
- Create: `evolution/initial_program.py`
- Test: `tests/test_evolution_candidate.py`

- [ ] **Step 1: Write failing tests** for the required `EvolvedStrategy(EvolutionStrategyConfig)` contract, evolve markers, skeleton hashing, forbidden imports/calls/reflection, syntax errors, sell-to-open attempts, non-IOC orders, and changes outside the evolve block.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_evolution_candidate` and verify failure.
- [ ] **Step 3: Implement** AST validation and a frozen skeleton whose editable region contains only indicators, state, and entry/exit rules; trusted helper methods enforce fixed-notional BUY and close-only SELL market IOC orders.
- [ ] **Step 4: Run** the focused test and verify it passes.

### Task 4: Deterministic backtest metrics and promotion rules

**Files:**
- Create: `evolution/metrics.py`
- Create: `evolution/backtest.py`
- Create: `evolution/selection.py`
- Test: `tests/test_evolution_metrics.py`
- Test: `tests/test_evolution_backtest.py`

- [ ] **Step 1: Write failing tests** for fee-inclusive decimal returns, drawdown, profit factor, exposure, forced close, no snapshot-based position counting, screen/fold rejection rules, the exact combined-score equation, baselines, deterministic reruns, and feasibility gates.
- [ ] **Step 2: Run** both focused test modules and verify failure.
- [ ] **Step 3: Implement** immutable metric dataclasses and scoring first, then a Nautilus `BacktestEngine` harness using independent CASH engines, 100,000 USDT, `BookType.L1_MBP`, fixed 10,000 USDT notional, market IOC, 10 bps per side, minute discovery quotes, and one-second delayed validation/holdout execution.
- [ ] **Step 4: Implement** buy-and-hold and SMA 3/8 baselines through the same harness and top-10 validation/once-only holdout selection.
- [ ] **Step 5: Run** focused tests and verify they pass.

### Task 5: Docker sandbox and evaluator cascade

**Files:**
- Create: `evolution/sandbox.py`
- Create: `evolution/sandbox_worker.py`
- Create: `evolution/evaluator.py`
- Create: `evolution/docker/Dockerfile`
- Test: `tests/test_evolution_sandbox.py`
- Test: `tests/test_evolution_evaluator.py`

- [ ] **Step 1: Write failing tests** for exact Docker flags, sanitized environment, read-only discovery mount, tmpfs, outer timeout cleanup, bounded artifacts, and stable low scores for syntax, unsafe code, crash, NaN, short attempt, rejection, >10% loss, zero trades, and insufficient fold activity.
- [ ] **Step 2: Run** both focused modules and verify failure.
- [ ] **Step 3: Implement** a subprocess-based Docker launcher with `--network none`, read-only rootfs/mount, one CPU, 1 GiB, PID limit, dropped capabilities, no-new-privileges, explicit safe environment, JSON-only stdio, and force removal on timeout.
- [ ] **Step 4: Implement** the three evaluator stages and return OpenEvolve `EvaluationResult` when installed, with aggregate-only redacted artifacts.
- [ ] **Step 5: Run** focused tests and verify they pass without requiring Docker by mocking the process boundary; keep real isolation checks opt-in.

### Task 6: OpenEvolve configuration and resilient orchestration

**Files:**
- Create: `evolution/config.py`
- Create: `evolution/runner.py`
- Create: `evolution/__main__.py`
- Create: `evolution/configs/base.yaml`
- Modify: `pyproject.toml`
- Test: `tests/test_evolution_runner.py`

- [ ] **Step 1: Write failing tests** for the OpenRouter ensemble, environment-only API key, 3 islands, population/archive 200/50, migration/checkpoint 50/10, two evaluations, diff mode, fixed seed, no LLM feedback, per-instrument database/output isolation, redaction, 429-safe exit, and exact resume commands.
- [ ] **Step 2: Pin** `openevolve==0.3.2` with `uv add openevolve==0.3.2` and inspect its installed CLI/config types.
- [ ] **Step 3: Implement** generated redacted run configs and CLI commands for `build-data`, `evolve --iterations 30`, `resume --iterations 300`, `select`, and `report`; validate prerequisites before any external operation.
- [ ] **Step 4: Run** focused tests and verify they pass using a fake OpenEvolve process.

### Task 7: Reports, docs, ignore rules, and opt-in integration smoke

**Files:**
- Create: `evolution/report.py`
- Create: `docs/research/openevolve-strategy-evolution.md`
- Create: `tests/integration/test_evolution_integration.py`
- Modify: `.gitignore`
- Test: `tests/test_evolution_report.py`

- [ ] **Step 1: Write failing tests** that generated JSON/HTML reports label non-passing candidates `rejected` or `feature_candidate`, contain baseline comparisons, redact secrets, and export canonical alpha rows with only `ts_event,instrument_id,alpha_name,value`.
- [ ] **Step 2: Implement** deterministic JSON/HTML output and document commands, methodology, promotion limits, and the prohibition on holdout feedback.
- [ ] **Step 3: Add** ignored local dataset/output paths and an integration module skipped unless `RUN_EVOLUTION_INTEGRATION=1`.
- [ ] **Step 4: Run** focused tests and verify they pass.

### Task 8: Verification and review

**Files:**
- Review: all files created above and overlapping user changes only where explicitly required.

- [ ] **Step 1: Run** `uv run python -m unittest discover -s tests` and fix only regressions attributable to this work.
- [ ] **Step 2: Run** `uv run python -m compileall evolution tests` and a CLI `--help` smoke.
- [ ] **Step 3: Run** the repository code-review workflow, check for secrets and unsafe Docker defaults, and resolve all high/medium findings.
- [ ] **Step 4: Record** which integration checks were skipped because catalog, Docker, or OpenRouter credentials were unavailable; do not claim that three 30-iteration runs completed unless their artifacts exist.
