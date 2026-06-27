from __future__ import annotations

import argparse
import bisect
import csv
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_ALPHA_NAME = "confirmed_pressure_persistence_1m"


@dataclass(frozen=True)
class AlphaSignal:
    ts_event: int
    instrument_id: str
    alpha_name: str
    value: float


@dataclass(frozen=True)
class AlphaPoint:
    ts_event: int
    instrument_id: str
    value: float


@dataclass(frozen=True)
class FeaturePoint:
    ts_event: int
    flow_value: float


def build_confirmed_pressure_signals(
    alpha_path: Path,
    feature_path: Path,
    bucket_seconds: int = 60,
    flow_column: str = "trade_imbalance",
    alpha_name: str | None = None,
) -> list[AlphaSignal]:
    if bucket_seconds <= 0:
        raise ValueError("bucket_seconds must be positive")
    if flow_column not in {"trade_imbalance", "volume_imbalance"}:
        raise ValueError("flow_column must be trade_imbalance or volume_imbalance")

    alpha_points = _read_alpha_points(alpha_path)
    feature_points = _read_feature_points(feature_path, flow_column)
    if not alpha_points or not feature_points:
        return []

    interval_ns = bucket_seconds * 1_000_000_000
    feature_times = [point.ts_event for point in feature_points]
    bucket_sums: dict[int, float] = {}
    bucket_counts: dict[int, int] = {}
    bucket_instruments: dict[int, str] = {}

    for alpha in alpha_points:
        feature_index = bisect.bisect_right(feature_times, alpha.ts_event) - 1
        if feature_index < 0:
            continue
        bucket = alpha.ts_event // interval_ns
        bucket_sums[bucket] = bucket_sums.get(bucket, 0.0) + _confirmed_pressure_contribution(
            alpha.value,
            feature_points[feature_index].flow_value,
        )
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        bucket_instruments.setdefault(bucket, alpha.instrument_id)

    signal_name = alpha_name or _alpha_name_for(bucket_seconds)
    return [
        AlphaSignal(
            ts_event=(bucket + 1) * interval_ns,
            instrument_id=bucket_instruments[bucket],
            alpha_name=signal_name,
            value=bucket_sums[bucket] / bucket_counts[bucket],
        )
        for bucket in sorted(bucket_sums)
        if bucket_counts[bucket] > 0
    ]


def write_signals_csv(signals: Iterable[AlphaSignal], output_path: Path) -> int:
    rows = [asdict(signal) for signal in signals]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["ts_event", "instrument_id", "alpha_name", "value"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _confirmed_pressure_contribution(book_value: float, flow_value: float) -> float:
    book_sign = _sign(book_value)
    flow_sign = _sign(flow_value)
    if book_sign > 0 and flow_sign > 0:
        return 1.0
    if book_sign < 0 and flow_sign < 0:
        return -1.0
    return 0.0


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _alpha_name_for(bucket_seconds: int) -> str:
    if bucket_seconds % 60 == 0:
        return f"confirmed_pressure_persistence_{bucket_seconds // 60}m"
    return f"confirmed_pressure_persistence_{bucket_seconds}s"


def _read_alpha_points(source_path: Path) -> list[AlphaPoint]:
    points: list[AlphaPoint] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            points.append(
                AlphaPoint(
                    ts_event=int(row["ts_event"]),
                    instrument_id=row["instrument_id"],
                    value=float(row["value"]),
                ),
            )
    return sorted(points, key=lambda point: point.ts_event)


def _read_feature_points(source_path: Path, flow_column: str) -> list[FeaturePoint]:
    points: list[FeaturePoint] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            points.append(
                FeaturePoint(
                    ts_event=int(row["ts_event"]),
                    flow_value=float(row[flow_column]),
                ),
            )
    return sorted(points, key=lambda point: point.ts_event)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate confirmed pressure persistence alpha from imbalance and signed flow CSVs.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--feature-source", type=Path, required=True)
    parser.add_argument("--bucket-seconds", type=int, default=60)
    parser.add_argument(
        "--flow-column",
        choices=["trade_imbalance", "volume_imbalance"],
        default="trade_imbalance",
    )
    parser.add_argument("--alpha-name")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/alphas/confirmed_pressure_persistence.csv"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    signals = build_confirmed_pressure_signals(
        args.source,
        args.feature_source,
        bucket_seconds=args.bucket_seconds,
        flow_column=args.flow_column,
        alpha_name=args.alpha_name,
    )
    rows_written = write_signals_csv(signals, args.output)
    print(f"wrote {rows_written} confirmed pressure persistence rows to {args.output}")
    print(f"source={args.source}")
    print(f"feature_source={args.feature_source}")
    print(f"bucket_seconds={args.bucket_seconds}")
    print(f"flow_column={args.flow_column}")


if __name__ == "__main__":
    main()
