from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

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
) -> list[PriceRow]:
    ticks = list(trade_ticks)
    if max_rows is not None:
        ticks = _downsample(ticks, max_rows)

    return [
        PriceRow(
            ts_event=getattr(tick, "ts_event"),
            instrument_id=str(getattr(tick, "instrument_id")),
            price=float(str(getattr(tick, "price"))),
        )
        for tick in ticks
    ]


def load_trade_prices(
    instrument_id: str,
    start: str,
    end: str,
    max_rows: int | None = None,
) -> list[PriceRow]:
    catalog = make_catalog()
    trade_ticks = catalog.trade_ticks(
        instrument_ids=[InstrumentId.from_str(instrument_id)],
        start=start,
        end=end,
    )
    return trade_ticks_to_price_rows(trade_ticks, max_rows=max_rows)


def write_price_rows_csv(rows: Iterable[PriceRow], output_path: Path) -> int:
    output_rows = [asdict(row) for row in rows]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["ts_event", "instrument_id", "price"])
        writer.writeheader()
        writer.writerows(output_rows)
    return len(output_rows)


def _downsample(items: list[object], max_rows: int) -> list[object]:
    if max_rows <= 0:
        raise ValueError("max_rows must be positive")
    if len(items) <= max_rows:
        return items
    if max_rows == 1:
        return [items[0]]

    step = (len(items) - 1) / (max_rows - 1)
    return [items[round(index * step)] for index in range(max_rows)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export trade tick prices for alpha report overlays.")
    parser.add_argument("--instrument-id", default=DEFAULT_INSTRUMENT_ID)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--max-rows", type=int, default=8000)
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
        max_rows=args.max_rows,
    )
    rows_written = write_price_rows_csv(rows, args.output)
    print(f"wrote {rows_written} trade price rows to {args.output}")
    print(f"instrument_id={args.instrument_id}")
    print(f"start={args.start}")
    print(f"end={args.end}")


if __name__ == "__main__":
    main()
