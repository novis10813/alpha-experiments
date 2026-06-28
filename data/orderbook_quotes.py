from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from data.nautilus_catalog import make_catalog
from nautilus_trader.model.data import OrderBookDepth10


DEFAULT_INSTRUMENT_ID = "BTCUSDT.BINANCE"


@dataclass(frozen=True)
class QuoteRow:
    ts_event: int
    instrument_id: str
    bid: float
    ask: float
    mid: float
    spread: float
    spread_bps: float


def depths_to_quote_rows(
    depths: Iterable[object],
    resample_seconds: int | None = None,
) -> list[QuoteRow]:
    rows = [_quote_row_for(depth) for depth in depths]
    if resample_seconds is None:
        return rows
    if resample_seconds <= 0:
        raise ValueError("resample_seconds must be positive")
    return _resample_quotes(rows, resample_seconds)


def load_orderbook_quotes(
    instrument_id: str,
    start: str,
    end: str,
    resample_seconds: int | None = None,
) -> list[QuoteRow]:
    catalog = make_catalog()
    depths = catalog.query(
        OrderBookDepth10,
        identifiers=[instrument_id],
        start=start,
        end=end,
    )
    return depths_to_quote_rows(depths, resample_seconds=resample_seconds)


def write_quote_rows_csv(rows: Iterable[QuoteRow], output_path: Path) -> int:
    output_rows = [asdict(row) for row in rows]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["ts_event", "instrument_id", "bid", "ask", "mid", "spread", "spread_bps"],
        )
        writer.writeheader()
        writer.writerows(output_rows)
    return len(output_rows)


def _quote_row_for(depth: object) -> QuoteRow:
    bid = _best_price(getattr(depth, "bids"))
    ask = _best_price(getattr(depth, "asks"))
    mid = (bid + ask) / 2
    spread = ask - bid
    spread_bps = spread / mid * 10_000 if mid else 0.0
    return QuoteRow(
        ts_event=getattr(depth, "ts_event"),
        instrument_id=str(getattr(depth, "instrument_id")),
        bid=bid,
        ask=ask,
        mid=mid,
        spread=spread,
        spread_bps=spread_bps,
    )


def _best_price(levels: Iterable[object]) -> float:
    for level in levels:
        if level is not None:
            return float(str(getattr(level, "price")))
    return 0.0


def _resample_quotes(rows: list[QuoteRow], interval_seconds: int) -> list[QuoteRow]:
    interval_ns = interval_seconds * 1_000_000_000
    result: list[QuoteRow] = []
    current_bucket: int | None = None
    current_quote: QuoteRow | None = None
    previous_quote: QuoteRow | None = None

    for row in rows:
        bucket = row.ts_event // interval_ns
        if current_bucket is not None and bucket != current_bucket and current_quote is not None:
            previous_quote = _quote_at_bucket_end(current_quote, current_bucket, interval_ns)
            result.append(previous_quote)
            for empty_bucket in range(current_bucket + 1, bucket):
                result.append(_quote_at_bucket_end(previous_quote, empty_bucket, interval_ns))
        current_bucket = bucket
        current_quote = row

    if current_bucket is not None and current_quote is not None:
        result.append(_quote_at_bucket_end(current_quote, current_bucket, interval_ns))
    return result


def _quote_at_bucket_end(row: QuoteRow, bucket: int, interval_ns: int) -> QuoteRow:
    return QuoteRow(
        ts_event=(bucket + 1) * interval_ns,
        instrument_id=row.instrument_id,
        bid=row.bid,
        ask=row.ask,
        mid=row.mid,
        spread=row.spread,
        spread_bps=row.spread_bps,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export best bid/ask quotes from OrderBookDepth10 data.")
    parser.add_argument("--instrument-id", default=DEFAULT_INSTRUMENT_ID)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument(
        "--resample-seconds",
        type=int,
        help="Export the last best bid/ask quote in each fixed-width time interval.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/market/orderbook_quotes.csv"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_orderbook_quotes(
        instrument_id=args.instrument_id,
        start=args.start,
        end=args.end,
        resample_seconds=args.resample_seconds,
    )
    rows_written = write_quote_rows_csv(rows, args.output)
    print(f"wrote {rows_written} orderbook quote rows to {args.output}")
    print(f"instrument_id={args.instrument_id}")
    print(f"start={args.start}")
    print(f"end={args.end}")


if __name__ == "__main__":
    main()
