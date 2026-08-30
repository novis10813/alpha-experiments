# Five Green Streak Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a focused diagnostic experiment for the hypothesis that five consecutive bullish 1 minute K-bars are a bullish signal.

**Architecture:** Reuse the existing trade-price CSV to 1 minute K-bar path from `reports.kbar_return_report`. Add one focused report module that detects five-green events, computes long-side forward returns across configured horizons, applies cooldown de-overlap, and renders a compact HTML summary. Document the hypothesis as a factor note.

**Tech Stack:** Python 3.13, stdlib `dataclasses`, `csv`, `statistics`, existing `common.kbars`, existing `unittest` suite.

---

### Task 1: Add Five-Green Event Diagnostics

**Files:**
- Create: `reports/five_green_streak_report.py`
- Test: `tests/test_five_green_streak_report.py`

- [x] **Step 1: Write tests for detection, forward returns, cooldown, and HTML rendering**

Run: `uv run python -m unittest tests.test_five_green_streak_report`

Expected before implementation: import failure for `reports.five_green_streak_report`.

- [x] **Step 2: Implement minimal report module**

The module should:
- read a price CSV through `build_kbar_context`
- detect events when exactly the fifth consecutive bullish bar closes
- timestamp the event at the fifth bar `ts_event`
- calculate forward long returns from trigger close to future close
- summarize count, mean, median, hit rate, and percentile bands
- support cooldown in minutes to reduce adjacent duplicate events
- render an HTML report and print CLI summaries

- [x] **Step 3: Run focused tests**

Run: `uv run python -m unittest tests.test_five_green_streak_report`

Expected: PASS.

### Task 2: Document Research Hypothesis

**Files:**
- Create: `docs/research/factors/five_green_streak.md`

- [x] **Step 1: Add factor note**

The note should define the five-green rule, timestamp semantics, diagnostics command, and interpretation rules.

- [x] **Step 2: Link future evidence location**

The note should leave key findings as pending until a real catalog window is run.

### Task 3: Verify Full Unit Suite

**Files:**
- No source changes.

- [x] **Step 1: Run unit tests**

Run: `uv run python -m unittest discover -s tests`

Expected: PASS.
