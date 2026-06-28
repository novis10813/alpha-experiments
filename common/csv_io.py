from __future__ import annotations

import csv
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class AlphaPoint:
    ts_event: int
    instrument_id: str
    alpha_name: str
    value: float

    @property
    def timestamp(self) -> str:
        from common.time_series import ts_event_to_iso

        return ts_event_to_iso(self.ts_event)


@dataclass(frozen=True)
class PricePoint:
    ts_event: int
    instrument_id: str
    price: float


@dataclass(frozen=True)
class QuotePoint:
    ts_event: int
    instrument_id: str
    bid: float
    ask: float
    mid: float
    spread: float
    spread_bps: float


@dataclass(frozen=True)
class TradeFeaturePoint:
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
    flow_value: float | None = None


def read_alpha_points(source_path: Path) -> list[AlphaPoint]:
    points: list[AlphaPoint] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            points.append(
                AlphaPoint(
                    ts_event=int(row["ts_event"]),
                    instrument_id=row.get("instrument_id", ""),
                    alpha_name=row.get("alpha_name", ""),
                    value=float(row["value"]),
                ),
            )
    return sorted(points, key=lambda point: point.ts_event)


def read_price_points(source_path: Path) -> list[PricePoint]:
    points: list[PricePoint] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            points.append(
                PricePoint(
                    ts_event=int(row["ts_event"]),
                    instrument_id=row.get("instrument_id", ""),
                    price=float(row["price"]),
                ),
            )
    return sorted(points, key=lambda point: point.ts_event)


def read_quote_points(source_path: Path) -> list[QuotePoint]:
    points: list[QuotePoint] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            points.append(
                QuotePoint(
                    ts_event=int(row["ts_event"]),
                    instrument_id=row.get("instrument_id", ""),
                    bid=float(row["bid"]),
                    ask=float(row["ask"]),
                    mid=float(row["mid"]),
                    spread=float(row.get("spread", 0.0)),
                    spread_bps=float(row["spread_bps"]),
                ),
            )
    return sorted(points, key=lambda point: point.ts_event)


def read_trade_feature_points(source_path: Path, flow_column: str | None = None) -> list[TradeFeaturePoint]:
    points: list[TradeFeaturePoint] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            flow_value = float(row[flow_column]) if flow_column is not None else None
            points.append(
                TradeFeaturePoint(
                    ts_event=int(row["ts_event"]),
                    instrument_id=row.get("instrument_id", ""),
                    price=float(row["price"]),
                    volume=float(row["volume"]),
                    trade_count=int(row.get("trade_count") or 0),
                    buy_trade_count=int(row.get("buy_trade_count") or 0),
                    sell_trade_count=int(row.get("sell_trade_count") or 0),
                    buy_volume=float(row.get("buy_volume") or 0.0),
                    sell_volume=float(row.get("sell_volume") or 0.0),
                    signed_trade_count=int(row.get("signed_trade_count") or 0),
                    signed_volume=float(row.get("signed_volume") or 0.0),
                    trade_imbalance=float(row.get("trade_imbalance") or 0.0),
                    volume_imbalance=float(row.get("volume_imbalance") or 0.0),
                    flow_value=flow_value,
                ),
            )
    return sorted(points, key=lambda point: point.ts_event)


def first_column_value(source_path: Path, column: str) -> str:
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        first = next(reader, None)
        if first is None:
            return ""
        return first[column]


def write_dataclass_csv(rows: Iterable[object], output_path: Path, fieldnames: list[str]) -> int:
    output_rows = [asdict(row) for row in rows]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)
    return len(output_rows)
