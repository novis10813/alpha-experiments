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
