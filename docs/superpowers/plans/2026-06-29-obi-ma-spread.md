# OBI MA Spread Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether 5 minute average order book imbalance above 15 minute average order book imbalance predicts bullish forward returns.

**Architecture:** Read existing 1 minute K-bar plus order book imbalance CSV rows produced by `data.kbar_orderbook_imbalance`. Compute rolling OBI averages using completed bars only, emit diagnostic events for bullish spread states, and summarize long-side forward returns by horizon, cooldown, and cost.

**Tech Stack:** Python 3.13, stdlib `csv`, `dataclasses`, `statistics`, existing `unittest`.

---

### Task 1: Add OBI MA Spread Report

**Files:**
- Create: `reports/obi_ma_spread_report.py`
- Test: `tests/test_obi_ma_spread_report.py`

- [x] **Step 1: Write tests**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run python -m unittest tests.test_obi_ma_spread_report`

Expected before implementation: import failure for `reports.obi_ma_spread_report`.

- [x] **Step 2: Implement report**

The report should compute:
- `obi_short_mean`: rolling 5 bar mean by default;
- `obi_long_mean`: rolling 15 bar mean by default;
- `obi_spread`: `obi_short_mean - obi_long_mean`;
- event groups:
  - `spread_positive`: `obi_spread > 0`;
  - `spread_positive_short_positive`: `obi_spread > 0 and obi_short_mean > 0`.

- [x] **Step 3: Run focused tests**

Expected: PASS.

### Task 2: Run Existing BTC Sample

**Files:**
- Output: `outputs/reports/obi_ma_spread_BTCUSDT_2026-06-17.html`

- [x] **Step 1: Run report on existing full-day BTC kbar imbalance CSV**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m reports.obi_ma_spread_report \
  --source outputs/market/kbar_orderbook_imbalance_BTCUSDT_2026-06-17_1m_complete.csv \
  --short-window 5 \
  --long-window 15 \
  --horizons-minutes 1 3 5 10 15 30 \
  --cooldown-minutes 0 5 15 \
  --cost-bps 0 2 5 10 \
  --output outputs/reports/obi_ma_spread_BTCUSDT_2026-06-17.html
```

### Task 3: Document First-Pass Result

**Files:**
- Create: `docs/research/factors/obi_ma_spread.md`

- [x] **Step 1: Record hypothesis, command, and result**

- [x] **Step 2: Verify full unit suite**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run python -m unittest discover -s tests`
