from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from alphas.orderbook_imbalance import orderbook_imbalance_value
from common.csv_io import write_dataclass_csv
from common.time_series import NS_PER_SECOND
from common.time_series import ts_event_to_iso
from data.nautilus_catalog import make_catalog
from nautilus_trader.model.data import OrderBookDepth10
from nautilus_trader.model.identifiers import InstrumentId


DEFAULT_INSTRUMENT_ID = "BTCUSDT.BINANCE"
IMBALANCE_BASES = {"mean", "volume", "trade_count"}


@dataclass(frozen=True)
class KbarOrderbookImbalanceRow:
    start_time: int
    end_time: int
    ts_event: int
    timestamp: str
    instrument_id: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int
    trade_id_start: int
    trade_id_end: int
    expected_trade_count: int
    trade_id_gap_count: int
    expected_coverage_count: int
    orderbook_coverage_count: int
    orderbook_sample_count: int
    orderbook_imbalance_mean: float
    orderbook_imbalance_last: float
    orderbook_imbalance_min: float
    orderbook_imbalance_max: float
    imbalance_basis: str
    imbalance_value: float
    imbalance_x_volume: float
    imbalance_x_trade_count: float


@dataclass(frozen=True)
class _TradeBucket:
    instrument_id: str
    bucket: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int
    trade_id_start: int
    trade_id_end: int
    expected_trade_count: int
    trade_id_gap_count: int


@dataclass(frozen=True)
class _OrderBookBucket:
    instrument_id: str
    bucket: int
    sample_count: int
    covered_intervals: frozenset[int]
    mean: float
    last: float
    min_value: float
    max_value: float


def kbar_orderbook_imbalance_rows(
    trade_ticks: Iterable[object],
    depths: Iterable[object],
    interval_seconds: int = 60,
    imbalance_basis: str = "mean",
    orderbook_coverage_seconds: int = 1,
) -> list[KbarOrderbookImbalanceRow]:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    if orderbook_coverage_seconds <= 0:
        raise ValueError("orderbook_coverage_seconds must be positive")
    if interval_seconds % orderbook_coverage_seconds != 0:
        raise ValueError("interval_seconds must be divisible by orderbook_coverage_seconds")
    if imbalance_basis not in IMBALANCE_BASES:
        raise ValueError("imbalance_basis must be mean, volume, or trade_count")

    interval_ns = interval_seconds * NS_PER_SECOND
    coverage_ns = orderbook_coverage_seconds * NS_PER_SECOND
    expected_coverage_count = interval_seconds // orderbook_coverage_seconds
    trade_buckets = _trade_buckets(trade_ticks, interval_ns)
    orderbook_buckets = _orderbook_buckets(depths, interval_ns, coverage_ns)

    rows: list[KbarOrderbookImbalanceRow] = []
    for key in sorted(trade_buckets.keys() & orderbook_buckets.keys(), key=lambda item: (item[1], item[0])):
        trade_bucket = trade_buckets[key]
        orderbook_bucket = orderbook_buckets[key]
        if trade_bucket.trade_id_gap_count != 0:
            continue
        if len(orderbook_bucket.covered_intervals) != expected_coverage_count:
            continue

        start_time = trade_bucket.bucket * interval_ns
        end_time = start_time + interval_ns
        imbalance_x_volume = orderbook_bucket.mean * trade_bucket.volume
        imbalance_x_trade_count = orderbook_bucket.mean * trade_bucket.trade_count
        rows.append(
            KbarOrderbookImbalanceRow(
                start_time=start_time,
                end_time=end_time,
                ts_event=end_time,
                timestamp=ts_event_to_iso(end_time),
                instrument_id=trade_bucket.instrument_id,
                open=trade_bucket.open,
                high=trade_bucket.high,
                low=trade_bucket.low,
                close=trade_bucket.close,
                volume=trade_bucket.volume,
                trade_count=trade_bucket.trade_count,
                trade_id_start=trade_bucket.trade_id_start,
                trade_id_end=trade_bucket.trade_id_end,
                expected_trade_count=trade_bucket.expected_trade_count,
                trade_id_gap_count=trade_bucket.trade_id_gap_count,
                expected_coverage_count=expected_coverage_count,
                orderbook_coverage_count=len(orderbook_bucket.covered_intervals),
                orderbook_sample_count=orderbook_bucket.sample_count,
                orderbook_imbalance_mean=orderbook_bucket.mean,
                orderbook_imbalance_last=orderbook_bucket.last,
                orderbook_imbalance_min=orderbook_bucket.min_value,
                orderbook_imbalance_max=orderbook_bucket.max_value,
                imbalance_basis=imbalance_basis,
                imbalance_value=_imbalance_value(
                    imbalance_basis,
                    orderbook_bucket.mean,
                    imbalance_x_volume,
                    imbalance_x_trade_count,
                ),
                imbalance_x_volume=imbalance_x_volume,
                imbalance_x_trade_count=imbalance_x_trade_count,
            ),
        )
    return rows


def load_kbar_orderbook_imbalance_rows(
    instrument_id: str,
    start: str,
    end: str,
    interval_seconds: int = 60,
    imbalance_basis: str = "mean",
    orderbook_coverage_seconds: int = 1,
) -> list[KbarOrderbookImbalanceRow]:
    catalog = make_catalog()
    trade_ticks = catalog.trade_ticks(
        instrument_ids=[InstrumentId.from_str(instrument_id)],
        start=start,
        end=end,
    )
    depths = catalog.query(
        OrderBookDepth10,
        identifiers=[instrument_id],
        start=start,
        end=end,
    )
    return kbar_orderbook_imbalance_rows(
        trade_ticks,
        depths,
        interval_seconds=interval_seconds,
        imbalance_basis=imbalance_basis,
        orderbook_coverage_seconds=orderbook_coverage_seconds,
    )


def write_kbar_orderbook_imbalance_csv(
    rows: Iterable[KbarOrderbookImbalanceRow],
    output_path: Path,
) -> int:
    return write_dataclass_csv(
        rows,
        output_path,
        [
            "start_time",
            "end_time",
            "ts_event",
            "timestamp",
            "instrument_id",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "trade_count",
            "trade_id_start",
            "trade_id_end",
            "expected_trade_count",
            "trade_id_gap_count",
            "expected_coverage_count",
            "orderbook_coverage_count",
            "orderbook_sample_count",
            "orderbook_imbalance_mean",
            "orderbook_imbalance_last",
            "orderbook_imbalance_min",
            "orderbook_imbalance_max",
            "imbalance_basis",
            "imbalance_value",
            "imbalance_x_volume",
            "imbalance_x_trade_count",
        ],
    )


def _trade_buckets(
    trade_ticks: Iterable[object],
    interval_ns: int,
) -> dict[tuple[str, int], _TradeBucket]:
    sorted_ticks = sorted(
        enumerate(trade_ticks),
        key=lambda item: (str(getattr(item[1], "instrument_id")), int(getattr(item[1], "ts_event")), item[0]),
    )
    buckets: dict[tuple[str, int], _TradeBucket] = {}
    current_key: tuple[str, int] | None = None
    prices: list[float] = []
    trade_ids: list[int] = []
    volume = 0.0

    for _, tick in sorted_ticks:
        instrument_id = str(getattr(tick, "instrument_id"))
        tick_ts_event = int(getattr(tick, "ts_event"))
        bucket = tick_ts_event // interval_ns
        key = (instrument_id, bucket)
        if current_key is not None and key != current_key:
            buckets[current_key] = _make_trade_bucket(current_key, prices, volume, trade_ids)
            prices = []
            trade_ids = []
            volume = 0.0

        current_key = key
        prices.append(float(str(getattr(tick, "price"))))
        trade_ids.append(int(str(getattr(tick, "trade_id"))))
        volume += float(str(getattr(tick, "size")))

    if current_key is not None and prices:
        buckets[current_key] = _make_trade_bucket(current_key, prices, volume, trade_ids)
    return buckets


def _orderbook_buckets(
    depths: Iterable[object],
    interval_ns: int,
    coverage_ns: int,
) -> dict[tuple[str, int], _OrderBookBucket]:
    sorted_depths = sorted(
        enumerate(depths),
        key=lambda item: (str(getattr(item[1], "instrument_id")), int(getattr(item[1], "ts_event")), item[0]),
    )
    buckets: dict[tuple[str, int], _OrderBookBucket] = {}
    current_key: tuple[str, int] | None = None
    values: list[float] = []
    covered_intervals: set[int] = set()

    for _, depth in sorted_depths:
        instrument_id = str(getattr(depth, "instrument_id"))
        depth_ts_event = int(getattr(depth, "ts_event"))
        bucket = depth_ts_event // interval_ns
        key = (instrument_id, bucket)
        if current_key is not None and key != current_key:
            buckets[current_key] = _make_orderbook_bucket(current_key, values, covered_intervals)
            values = []
            covered_intervals = set()

        current_key = key
        values.append(orderbook_imbalance_value(depth))
        covered_intervals.add((depth_ts_event % interval_ns) // coverage_ns)

    if current_key is not None and values:
        buckets[current_key] = _make_orderbook_bucket(current_key, values, covered_intervals)
    return buckets


def _make_trade_bucket(
    key: tuple[str, int],
    prices: list[float],
    volume: float,
    trade_ids: list[int],
) -> _TradeBucket:
    instrument_id, bucket = key
    trade_id_start = trade_ids[0]
    trade_id_end = trade_ids[-1]
    expected_trade_count = trade_id_end - trade_id_start + 1
    return _TradeBucket(
        instrument_id=instrument_id,
        bucket=bucket,
        open=prices[0],
        high=max(prices),
        low=min(prices),
        close=prices[-1],
        volume=volume,
        trade_count=len(prices),
        trade_id_start=trade_id_start,
        trade_id_end=trade_id_end,
        expected_trade_count=expected_trade_count,
        trade_id_gap_count=expected_trade_count - len(set(trade_ids)),
    )


def _make_orderbook_bucket(
    key: tuple[str, int],
    values: list[float],
    covered_intervals: set[int],
) -> _OrderBookBucket:
    instrument_id, bucket = key
    return _OrderBookBucket(
        instrument_id=instrument_id,
        bucket=bucket,
        sample_count=len(values),
        covered_intervals=frozenset(covered_intervals),
        mean=sum(values) / len(values),
        last=values[-1],
        min_value=min(values),
        max_value=max(values),
    )


def _imbalance_value(
    basis: str,
    mean: float,
    imbalance_x_volume: float,
    imbalance_x_trade_count: float,
) -> float:
    if basis == "volume":
        return imbalance_x_volume
    if basis == "trade_count":
        return imbalance_x_trade_count
    return mean


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export complete 1m kbar rows aligned with order book imbalance.")
    parser.add_argument("--instrument-id", default=DEFAULT_INSTRUMENT_ID)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument(
        "--orderbook-coverage-seconds",
        type=int,
        default=1,
        help="Require at least one orderbook sample in every coverage sub-interval.",
    )
    parser.add_argument(
        "--imbalance-basis",
        choices=sorted(IMBALANCE_BASES),
        default="mean",
        help="Select the value column: raw mean imbalance, mean imbalance times volume, or mean imbalance times trade count.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/market/kbar_orderbook_imbalance.csv"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_kbar_orderbook_imbalance_rows(
        instrument_id=args.instrument_id,
        start=args.start,
        end=args.end,
        interval_seconds=args.interval_seconds,
        imbalance_basis=args.imbalance_basis,
        orderbook_coverage_seconds=args.orderbook_coverage_seconds,
    )
    rows_written = write_kbar_orderbook_imbalance_csv(rows, args.output)
    print(f"wrote {rows_written} aligned kbar imbalance rows to {args.output}")
    print(f"instrument_id={args.instrument_id}")
    print(f"start={args.start}")
    print(f"end={args.end}")
    print(f"interval_seconds={args.interval_seconds}")
    print(f"orderbook_coverage_seconds={args.orderbook_coverage_seconds}")
    print(f"imbalance_basis={args.imbalance_basis}")


if __name__ == "__main__":
    main()
