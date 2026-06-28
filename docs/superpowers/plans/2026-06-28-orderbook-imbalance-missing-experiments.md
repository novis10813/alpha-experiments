# Orderbook Imbalance Missing Experiments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the missing validation experiments needed to decide whether order book imbalance has executable value after quote prices, costs, delay, overlap, and regimes.

**Architecture:** Keep each experiment as a focused CSV/report module following the existing `data/`, `reports/`, and `tests/` layout. Start with quote-based executable returns because every later transaction-cost and delay check depends on bid/ask prices rather than trade prices.

**Tech Stack:** Python 3.13, `uv`, stdlib `csv`/`bisect`/`dataclasses`, Nautilus `OrderBookDepth10`, existing `unittest` tests.

---

### Task 1: Quote Export And Executable Return Screen

**Files:**
- Create: `data/orderbook_quotes.py`
- Create: `reports/executable_return_report.py`
- Create: `tests/test_orderbook_quotes.py`
- Create: `tests/test_executable_return_report.py`
- Modify: `docs/research/factors/orderbook_imbalance_feature.md`

- [x] **Step 1: Write quote-export tests**

Add fake depth rows with top bid/ask levels and verify `depths_to_quote_rows()` emits:

```text
ts_event,instrument_id,bid,ask,mid,spread,spread_bps
```

Also verify optional fixed-width resampling keeps the last quote in each bucket and carries the previous quote through empty buckets.

- [x] **Step 2: Implement quote exporter**

Implement `data.orderbook_quotes` with:

```python
QuoteRow(ts_event, instrument_id, bid, ask, mid, spread, spread_bps)
depths_to_quote_rows(depths, resample_seconds=None)
load_orderbook_quotes(instrument_id, start, end, resample_seconds=None)
write_quote_rows_csv(rows, output_path)
```

Use `ParquetDataCatalog.query(OrderBookDepth10, ...)` through `make_catalog()`.

- [x] **Step 3: Write executable-return tests**

Use small alpha and quote CSVs. Verify:

```text
positive alpha: enter long at current ask, exit at future bid
negative alpha: enter short at current bid, exit at future ask
zero alpha: no position, executable directional return is 0
delay: current quote comes from ts_event + delay_seconds
cost_bps: net return = gross return - cost_bps / 10000
```

- [x] **Step 4: Implement executable-return report**

Implement `reports.executable_return_report` with a context builder and CLI:

```bash
uv run python -m reports.executable_return_report \
  outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv \
  --quote-source outputs/market/orderbook_quotes_BTCUSDT_2026-06-18_2026-06-25_1s.csv \
  --horizons-seconds 10 30 60 \
  --delay-seconds 0 1 5 10 \
  --cost-bps 0 2 5 10 \
  --output outputs/reports/orderbook_imbalance_executable_returns_BTCUSDT_2026-06-18_2026-06-25.html
```

- [x] **Step 5: Run focused tests**

Run:

```bash
uv run python -m unittest tests.test_orderbook_quotes tests.test_executable_return_report
```

Expected: all focused tests pass.

- [x] **Step 6: Generate quote CSV and executable report if catalog credentials are available**

Run:

```bash
uv run python -m data.orderbook_quotes \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-06-18T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --resample-seconds 1 \
  --output outputs/market/orderbook_quotes_BTCUSDT_2026-06-18_2026-06-25_1s.csv
```

Then run the executable-return report command from Step 4.

- [x] **Step 7: Document findings**

Add a short section to `docs/research/factors/orderbook_imbalance_feature.md` with gross/net executable-return summaries and whether the raw trade-price edge survives bid/ask execution.

### Task 2: Spread Regime Screen

**Files:**
- Create: `reports/spread_regime_report.py`
- Create: `tests/test_spread_regime_report.py`
- Modify: `docs/research/factors/orderbook_imbalance_feature.md`

- [x] Split executable-return points by spread bps median, p75, and p90.
- [x] Report whether high-spread regimes explain or destroy the raw edge.
- [x] Document whether spread should be a veto condition.

### Task 3: Strict Event Clustering

**Files:**
- Create: `reports/clustered_event_report.py`
- Create: `tests/test_clustered_event_report.py`
- Modify: `docs/research/factors/orderbook_imbalance_feature.md`

- [x] Collapse consecutive extreme imbalance or pressure states into one event.
- [x] Recompute forward returns on clustered events only.
- [x] Compare clustered counts and returns against raw snapshot counts.

### Task 4: Dense Signed Flow Four-Quadrant Screen

**Files:**
- Create: `reports/dense_signed_flow_report.py`
- Create: `tests/test_dense_signed_flow_report.py`
- Modify: `docs/research/factors/orderbook_imbalance_feature.md`

- [x] Combine trade density regimes with signed-flow quadrants.
- [x] Test whether confirmed pressure is strongest specifically during high-density flow.
- [x] Document trade-count and signed-volume versions.

### Task 5: Multi-Instrument Validation

**Files:**
- Modify existing alpha/report commands only if needed.
- Modify: `docs/research/factors/orderbook_imbalance_feature.md`

- [x] Repeat core executable-return and pressure-persistence diagnostics for `ETHUSDT.BINANCE`.
- [x] Repeat core executable-return and pressure-persistence diagnostics for `BNBUSDT.BINANCE`.
- [x] Document whether the result is BTC-specific or cross-instrument.
