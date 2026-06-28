from __future__ import annotations

"""Export raw order book imbalance in the canonical alpha row shape.

The row shape is useful for shared diagnostics, but the research conclusion is
that raw order book imbalance is a feature candidate rather than a standalone
tradable alpha.
"""

import argparse
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Iterable

from common.csv_io import write_dataclass_csv
from data.nautilus_catalog import make_catalog
from nautilus_trader.model.data import OrderBookDepth10


DEFAULT_ALPHA_NAME = "orderbook_imbalance_depth10"
DEFAULT_INSTRUMENT_ID = "BTCUSDT.BINANCE"


@dataclass(frozen=True)
class AlphaSignal:
    ts_event: int
    instrument_id: str
    alpha_name: str
    value: float


def _level_size(level: object) -> float:
    size = getattr(level, "size", 0)
    return float(str(size))


def _side_size(levels: Iterable[object]) -> float:
    return sum(_level_size(level) for level in levels if level is not None)


def orderbook_imbalance_value(depth: object) -> float:
    bid_size = _side_size(getattr(depth, "bids"))
    ask_size = _side_size(getattr(depth, "asks"))
    total_size = bid_size + ask_size
    if total_size == 0:
        return 0.0
    return (bid_size - ask_size) / total_size


def orderbook_imbalance_signals(
    depths: Iterable[object],
    alpha_name: str = DEFAULT_ALPHA_NAME,
) -> list[AlphaSignal]:
    return [
        AlphaSignal(
            ts_event=getattr(depth, "ts_event"),
            instrument_id=str(getattr(depth, "instrument_id")),
            alpha_name=alpha_name,
            value=orderbook_imbalance_value(depth),
        )
        for depth in depths
    ]


def past_week_range(now: datetime | None = None) -> tuple[str, str]:
    end = now or datetime.now(UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    end = end.astimezone(UTC).replace(microsecond=0)
    start = end - timedelta(days=7)
    return (_format_utc(start), _format_utc(end))


def load_past_week_orderbook_imbalance(
    instrument_id: str = DEFAULT_INSTRUMENT_ID,
    alpha_name: str = DEFAULT_ALPHA_NAME,
    start: str | None = None,
    end: str | None = None,
) -> list[AlphaSignal]:
    if start is None or end is None:
        default_start, default_end = past_week_range()
        start = start or default_start
        end = end or default_end

    catalog = make_catalog()
    depths = catalog.query(
        OrderBookDepth10,
        identifiers=[instrument_id],
        start=start,
        end=end,
    )
    return orderbook_imbalance_signals(depths, alpha_name=alpha_name)


def write_signals_csv(signals: Iterable[AlphaSignal], output_path: Path) -> int:
    return write_dataclass_csv(signals, output_path, ["ts_event", "instrument_id", "alpha_name", "value"])


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args() -> argparse.Namespace:
    default_start, default_end = past_week_range()
    parser = argparse.ArgumentParser(
        description="Generate order book imbalance alpha signals from Nautilus catalog depth data.",
    )
    parser.add_argument("--instrument-id", default=DEFAULT_INSTRUMENT_ID)
    parser.add_argument("--alpha-name", default=DEFAULT_ALPHA_NAME)
    parser.add_argument("--start", default=default_start)
    parser.add_argument("--end", default=default_end)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/alphas/orderbook_imbalance.csv"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    signals = load_past_week_orderbook_imbalance(
        instrument_id=args.instrument_id,
        alpha_name=args.alpha_name,
        start=args.start,
        end=args.end,
    )
    rows_written = write_signals_csv(signals, args.output)
    print(f"wrote {rows_written} {args.alpha_name} rows to {args.output}")
    print(f"instrument_id={args.instrument_id}")
    print(f"start={args.start}")
    print(f"end={args.end}")


if __name__ == "__main__":
    main()
