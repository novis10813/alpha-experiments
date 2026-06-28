from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from common.csv_io import write_dataclass_csv
from common.resampling import resample_last_by_bucket
from common.time_series import downsample
from data.nautilus_catalog import make_catalog
from nautilus_trader.model.identifiers import InstrumentId


DEFAULT_INSTRUMENT_ID = "BTCUSDT.BINANCE"


@dataclass(frozen=True)
class PriceRow:
    ts_event: int
    instrument_id: str
    price: float


def trade_ticks_to_price_rows(
    trade_ticks: Iterable[object],
    max_rows: int | None = None,
    resample_seconds: int | None = None,
) -> list[PriceRow]:
    if resample_seconds is not None:
        ticks = resample_last_by_bucket(
            trade_ticks,
            resample_seconds,
            lambda tick: getattr(tick, "ts_event"),
            _price_row_at_ts_event,
        )
    else:
        ticks = [
            PriceRow(
                ts_event=getattr(tick, "ts_event"),
                instrument_id=str(getattr(tick, "instrument_id")),
                price=float(str(getattr(tick, "price"))),
            )
            for tick in trade_ticks
        ]

    if max_rows is not None:
        ticks = downsample(ticks, max_rows)

    return ticks


def load_trade_prices(
    instrument_id: str,
    start: str,
    end: str,
    max_rows: int | None = None,
    resample_seconds: int | None = None,
) -> list[PriceRow]:
    catalog = make_catalog()
    trade_ticks = catalog.trade_ticks(
        instrument_ids=[InstrumentId.from_str(instrument_id)],
        start=start,
        end=end,
    )
    return trade_ticks_to_price_rows(
        trade_ticks,
        max_rows=max_rows,
        resample_seconds=resample_seconds,
    )


def write_price_rows_csv(rows: Iterable[PriceRow], output_path: Path) -> int:
    return write_dataclass_csv(rows, output_path, ["ts_event", "instrument_id", "price"])


def resolve_max_rows(
    max_rows: int,
    no_downsample: bool = False,
    resample_seconds: int | None = None,
) -> int | None:
    if no_downsample or resample_seconds is not None:
        return None
    return max_rows


def _price_row_at_ts_event(tick: object, ts_event: int) -> PriceRow:
    return PriceRow(
        ts_event=ts_event,
        instrument_id=str(getattr(tick, "instrument_id")),
        price=float(str(getattr(tick, "price"))),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export trade tick prices for alpha report overlays.")
    parser.add_argument("--instrument-id", default=DEFAULT_INSTRUMENT_ID)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--max-rows", type=int, default=8000)
    parser.add_argument(
        "--resample-seconds",
        type=int,
        help="Export the last trade price in each fixed-width time interval.",
    )
    parser.add_argument(
        "--no-downsample",
        action="store_true",
        help="Export all queried trade prices. Use this for forward-return diagnostics.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/market/trade_prices.csv"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_trade_prices(
        instrument_id=args.instrument_id,
        start=args.start,
        end=args.end,
        max_rows=resolve_max_rows(args.max_rows, args.no_downsample, args.resample_seconds),
        resample_seconds=args.resample_seconds,
    )
    rows_written = write_price_rows_csv(rows, args.output)
    print(f"wrote {rows_written} trade price rows to {args.output}")
    print(f"instrument_id={args.instrument_id}")
    print(f"start={args.start}")
    print(f"end={args.end}")


if __name__ == "__main__":
    main()
