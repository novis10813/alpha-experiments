# Pressure Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a 1 minute confirmed pressure persistence alpha derived from order book imbalance and signed trade flow.

**Architecture:** Add a focused alpha exporter that reads existing canonical imbalance CSV plus 1 second signed trade features, joins each imbalance event to the latest known signed flow row, and emits one canonical alpha row per completed time bucket. Use the existing relationship report to evaluate 1m, 3m, and 5m forward returns.

**Tech Stack:** Python 3.13, `uv`, stdlib `csv`/`bisect`/`dataclasses`, existing `unittest` and report tooling.

---

### Task 1: Confirmed Pressure Alpha

**Files:**
- Create: `alphas/pressure_persistence.py`
- Create: `tests/test_pressure_persistence.py`

- [ ] **Step 1: Write the failing tests**

Add tests that prove confirmed bid pressure contributes `+1`, confirmed ask pressure contributes `-1`, disagreement contributes `0`, bucket timestamps are the end of the bucket, and CSV output keeps the canonical alpha shape.

- [ ] **Step 2: Run the tests to verify RED**

Run: `uv run python -m unittest tests.test_pressure_persistence`

Expected: failure because `alphas.pressure_persistence` does not exist.

- [ ] **Step 3: Implement the alpha exporter**

Create `alphas/pressure_persistence.py` with:

- `build_confirmed_pressure_signals(alpha_path, feature_path, bucket_seconds=60, flow_column="trade_imbalance")`
- `write_signals_csv(signals, output_path)`
- CLI args for alpha source, feature source, output, bucket seconds, and flow column.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run: `uv run python -m unittest tests.test_pressure_persistence`

Expected: all tests pass.

### Task 2: Full Verification And Experiment

**Files:**
- Modify: `docs/research/factors/orderbook_imbalance_feature.md`
- Generate: `outputs/alphas/confirmed_pressure_persistence_BTCUSDT_2026-06-18_2026-06-25_1m.csv`
- Generate: `outputs/reports/confirmed_pressure_persistence_relationship_BTCUSDT_2026-06-18_2026-06-25_1m_3m_5m.html`

- [ ] **Step 1: Run the full test suite**

Run: `uv run python -m unittest discover -s tests`

Expected: all tests pass.

- [ ] **Step 2: Generate the 1 minute alpha**

Run:

```bash
uv run python -m alphas.pressure_persistence \
  outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv \
  --feature-source outputs/market/trade_features_BTCUSDT_2026-06-18_2026-06-25_1s_signed.csv \
  --bucket-seconds 60 \
  --output outputs/alphas/confirmed_pressure_persistence_BTCUSDT_2026-06-18_2026-06-25_1m.csv
```

- [ ] **Step 3: Generate the 1m/3m/5m relationship report**

Run:

```bash
uv run python -m reports.alpha_relationship_report \
  outputs/alphas/confirmed_pressure_persistence_BTCUSDT_2026-06-18_2026-06-25_1m.csv \
  --price-source outputs/market/trade_prices_BTCUSDT_2026-06-18_2026-06-25_1s.csv \
  --output outputs/reports/confirmed_pressure_persistence_relationship_BTCUSDT_2026-06-18_2026-06-25_1m_3m_5m.html \
  --horizons-seconds 60 180 300 \
  --bucket-count 10 \
  --max-points 8000
```

- [ ] **Step 4: Summarize the bucket spreads**

Use `build_relationship_context` to extract bucket summaries and record the top-bottom spread in the research note.

- [ ] **Step 5: Final verification**

Run: `uv run python -m unittest discover -s tests`

Expected: all tests pass.
