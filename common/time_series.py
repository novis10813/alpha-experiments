from __future__ import annotations

import bisect
from datetime import UTC
from datetime import datetime
from typing import Sequence
from typing import TypeVar


NS_PER_SECOND = 1_000_000_000

T = TypeVar("T")


def ts_event_to_iso(ts_event: int) -> str:
    return datetime.fromtimestamp(ts_event / NS_PER_SECOND, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def percentile(sorted_values: Sequence[float], percentile_value: float) -> float:
    if not sorted_values:
        raise ValueError("sorted_values must not be empty")
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = percentile_value * (len(sorted_values) - 1)
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def downsample(items: list[T], max_items: int) -> list[T]:
    if max_items <= 0:
        raise ValueError("max_items must be positive")
    if len(items) <= max_items:
        return items
    if max_items == 1:
        return [items[0]]
    step = (len(items) - 1) / (max_items - 1)
    return [items[round(index * step)] for index in range(max_items)]


def index_at_or_before(times: Sequence[int], ts_event: int) -> int:
    return bisect.bisect_right(times, ts_event) - 1


def index_at_or_after(times: Sequence[int], ts_event: int) -> int:
    return bisect.bisect_left(times, ts_event)


def require_dense_series(points: Sequence[object], shortest_horizon_seconds: int, label: str) -> None:
    if shortest_horizon_seconds <= 0:
        raise ValueError("shortest_horizon_seconds must be positive")
    if len(points) < 2:
        return
    max_gap_ns = shortest_horizon_seconds * NS_PER_SECOND
    previous = int(getattr(points[0], "ts_event"))
    for point in points[1:]:
        current = int(getattr(point, "ts_event"))
        if current - previous > max_gap_ns:
            raise RuntimeError(
                f"{label} is too sparse for {shortest_horizon_seconds}s horizon: "
                f"gap {(current - previous) / NS_PER_SECOND:g}s",
            )
        previous = current

