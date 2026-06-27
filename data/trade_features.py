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
class TradeFeatureRow:
    ts_event: int
    instrument_id: str
    price: float
    volume: float
    trade_count: int
    buy_trade_count: int
    sell_trade_count: int
    buy_volume: float
    sell_volume: float
    signed_trade_count: int
    signed_volume: float
    trade_imbalance: float
    volume_imbalance: float


def trade_ticks_to_feature_rows(
    trade_ticks: Iterable[object],
    resample_seconds: int = 1,
) -> list[TradeFeatureRow]:
    if resample_seconds <= 0:
        raise ValueError("resample_seconds must be positive")

    interval_ns = resample_seconds * 1_000_000_000
    rows: list[TradeFeatureRow] = []
    current_bucket: int | None = None
    current_tick: object | None = None
    current_volume = 0.0
    current_trade_count = 0
    current_buy_trade_count = 0
    current_sell_trade_count = 0
    current_buy_volume = 0.0
    current_sell_volume = 0.0
    previous_price: float | None = None
    previous_sign = 0

    for tick in trade_ticks:
        bucket = getattr(tick, "ts_event") // interval_ns
        if current_bucket is not None and bucket != current_bucket and current_tick is not None:
            rows.append(
                _feature_row(
                    current_tick,
                    current_volume,
                    current_trade_count,
                    current_buy_trade_count,
                    current_sell_trade_count,
                    current_buy_volume,
                    current_sell_volume,
                ),
            )
            current_volume = 0.0
            current_trade_count = 0
            current_buy_trade_count = 0
            current_sell_trade_count = 0
            current_buy_volume = 0.0
            current_sell_volume = 0.0
        current_bucket = bucket
        current_tick = tick
        price = _price(tick)
        size = _size(tick)
        sign = _tick_rule_sign(price, previous_price, previous_sign)
        if sign > 0:
            current_buy_trade_count += 1
            current_buy_volume += size
        elif sign < 0:
            current_sell_trade_count += 1
            current_sell_volume += size
        current_volume += size
        current_trade_count += 1
        previous_price = price
        previous_sign = sign

    if current_tick is not None:
        rows.append(
            _feature_row(
                current_tick,
                current_volume,
                current_trade_count,
                current_buy_trade_count,
                current_sell_trade_count,
                current_buy_volume,
                current_sell_volume,
            ),
        )
    return rows


def load_trade_features(
    instrument_id: str,
    start: str,
    end: str,
    resample_seconds: int = 1,
) -> list[TradeFeatureRow]:
    catalog = make_catalog()
    trade_ticks = catalog.trade_ticks(
        instrument_ids=[InstrumentId.from_str(instrument_id)],
        start=start,
        end=end,
    )
    return trade_ticks_to_feature_rows(trade_ticks, resample_seconds=resample_seconds)


def write_feature_rows_csv(rows: Iterable[TradeFeatureRow], output_path: Path) -> int:
    output_rows = [asdict(row) for row in rows]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "ts_event",
                "instrument_id",
                "price",
                "volume",
                "trade_count",
                "buy_trade_count",
                "sell_trade_count",
                "buy_volume",
                "sell_volume",
                "signed_trade_count",
                "signed_volume",
                "trade_imbalance",
                "volume_imbalance",
            ],
        )
        writer.writeheader()
        writer.writerows(output_rows)
    return len(output_rows)


def _feature_row(
    tick: object,
    volume: float,
    trade_count: int,
    buy_trade_count: int,
    sell_trade_count: int,
    buy_volume: float,
    sell_volume: float,
) -> TradeFeatureRow:
    signed_trade_count = buy_trade_count - sell_trade_count
    signed_volume = buy_volume - sell_volume
    return TradeFeatureRow(
        ts_event=getattr(tick, "ts_event"),
        instrument_id=str(getattr(tick, "instrument_id")),
        price=_price(tick),
        volume=volume,
        trade_count=trade_count,
        buy_trade_count=buy_trade_count,
        sell_trade_count=sell_trade_count,
        buy_volume=buy_volume,
        sell_volume=sell_volume,
        signed_trade_count=signed_trade_count,
        signed_volume=signed_volume,
        trade_imbalance=_imbalance(signed_trade_count, buy_trade_count + sell_trade_count),
        volume_imbalance=_imbalance(signed_volume, buy_volume + sell_volume),
    )


def _price(tick: object) -> float:
    return float(str(getattr(tick, "price")))


def _size(tick: object) -> float:
    return float(str(getattr(tick, "size")))


def _tick_rule_sign(price: float, previous_price: float | None, previous_sign: int) -> int:
    if previous_price is None:
        return 0
    if price > previous_price:
        return 1
    if price < previous_price:
        return -1
    return previous_sign


def _imbalance(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export resampled trade price and volume features.")
    parser.add_argument("--instrument-id", default=DEFAULT_INSTRUMENT_ID)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--resample-seconds", type=int, default=1)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/market/trade_features.csv"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_trade_features(
        instrument_id=args.instrument_id,
        start=args.start,
        end=args.end,
        resample_seconds=args.resample_seconds,
    )
    rows_written = write_feature_rows_csv(rows, args.output)
    print(f"wrote {rows_written} trade feature rows to {args.output}")
    print(f"instrument_id={args.instrument_id}")
    print(f"start={args.start}")
    print(f"end={args.end}")
    print(f"resample_seconds={args.resample_seconds}")


if __name__ == "__main__":
    main()
