from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from common.csv_io import write_dataclass_csv
from common.resampling import resample_last_by_bucket
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
    return resample_quote_rows(
        [_quote_row_for(depth) for depth in depths],
        resample_seconds,
    )


def resample_quote_rows(
    rows: list[QuoteRow],
    interval_seconds: int | None,
) -> list[QuoteRow]:
    if interval_seconds is None:
        return rows
    if interval_seconds <= 0:
        raise ValueError("resample_seconds must be positive")
    return _resample_quotes(rows, interval_seconds)


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
    return write_dataclass_csv(
        rows,
        output_path,
        ["ts_event", "instrument_id", "bid", "ask", "mid", "spread", "spread_bps"],
    )


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
    return resample_last_by_bucket(rows, interval_seconds, lambda row: row.ts_event, _quote_at_ts_event)


def _quote_at_ts_event(row: QuoteRow, ts_event: int) -> QuoteRow:
    return QuoteRow(
        ts_event=ts_event,
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
