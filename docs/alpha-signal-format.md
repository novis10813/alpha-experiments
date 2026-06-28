# Alpha Signal Format

This project treats an alpha as a time-indexed signal, not as a strategy, position,
or PnL stream. The first thing to standardize is the smallest useful storage unit
for an alpha value.

## Canonical row shape

The canonical alpha signal row is:

| Column | Meaning |
| --- | --- |
| `ts_event` | The event time when the signal value is known. |
| `instrument_id` | Nautilus instrument identifier, for example `BTCUSDT.BINANCE`. |
| `alpha_name` | Stable name for the alpha definition, for example `trade_imbalance_1m`. |
| `value` | Numeric alpha value at `ts_event` for `instrument_id`. |

For a one-off local experiment, `alpha_name` can feel redundant. It should still be
included once signals may be saved, compared, joined, or visualized together.

## Timestamp semantics

`ts_event` should mean "the time this signal is knowable from market data." It should
not mean file write time, report generation time, or backtest processing time.

This distinction matters because alpha research is sensitive to lookahead. If a
signal uses data through 10:01:00, then its timestamp must not imply it was available
before 10:01:00.

When there is ambiguity, prefer the conservative timestamp: the earliest time at
which all inputs used by the signal are actually available.

### Case Study: Lookahead Bias in Resampled Data

When resampling high-frequency data into fixed-width time buckets (e.g., 1-second or 1-minute intervals) for feature engineering, the generated timestamps must be handled with care.

A common pitfall is marking the output row's timestamp (`ts_event`) using the **timestamp of the last tick** inside the bucket (e.g., a trade tick at `10:00:58` within the `[10:00:00, 10:01:00)` interval), rather than the **bucket end time** (`10:01:00`).

In historical analysis, a signal generator processing an update at `10:00:59` would use binary search (`bisect_right`) to look up the latest available market feature. Since `10:00:59 >= 10:00:58`, it would retrieve the feature row for that bucket. However, the complete features of the `[10:00:00, 10:01:00)` bucket are not physically knowable in real-time until the bucket actually ends at `10:01:00`. This leaks future transaction information into the signal generator, creating **lookahead bias**.

**Rule of Thumb:**
For any aggregated or resampled data, the `ts_event` must always be marked as the **end of the aggregation interval** (i.e., `(bucket + 1) * interval`).

## What does not belong in the core signal

The core alpha table should stay narrow. These fields are useful, but they are
diagnostics or report-time joins rather than the alpha itself:

- price or mid price
- spread
- volume
- forward returns
- z-scores
- thresholds
- long/short trigger flags
- buckets or quantiles
- positions, orders, fills, PnL, or drawdown

Keeping the alpha row narrow makes it easier to store, compare, and reuse signals
across different reports and backtests.

## Diagnostics layer

Visualization should start as an alpha exploration report, not a full dashboard.
The report can derive extra columns from the canonical signal table and market data:

- price overlay around signal changes
- signal distribution
- non-zero or non-null signal coverage
- threshold event markers
- forward returns after signal events
- per-instrument stability checks

This gives each new alpha idea the same first-pass inspection path:

```text
Nautilus catalog data
-> alpha function
-> canonical signal table
-> diagnostics joins
-> HTML or static report
```

An independent dashboard can come later if there are many saved alphas, comparison
workflows, or interactive filtering needs. Until then, report generation keeps the
research loop simpler and easier to version.

## Storage guidance

The storage format can change later, but the logical schema should remain stable:

```text
ts_event, instrument_id, alpha_name, value
```

Possible physical formats include Parquet files, a local DuckDB database, or a
future catalog-like layout. The physical choice should not leak into alpha functions;
alpha functions should only need to return the canonical signal table.
