from __future__ import annotations

from typing import Callable
from typing import Iterable
from typing import TypeVar

from common.time_series import NS_PER_SECOND


T = TypeVar("T")
R = TypeVar("R")


def bucket_end_ts(bucket: int, interval_ns: int) -> int:
    return (bucket + 1) * interval_ns


def resample_last_by_bucket(
    items: Iterable[T],
    interval_seconds: int,
    ts_event: Callable[[T], int],
    make_row: Callable[[T, int], R],
) -> list[R]:
    if interval_seconds <= 0:
        raise ValueError("resample_seconds must be positive")

    interval_ns = interval_seconds * NS_PER_SECOND
    result: list[R] = []
    current_bucket: int | None = None
    current_item: T | None = None
    previous_output: R | None = None

    for item in items:
        bucket = ts_event(item) // interval_ns
        if current_bucket is not None and bucket != current_bucket and current_item is not None:
            previous_output = make_row(current_item, bucket_end_ts(current_bucket, interval_ns))
            result.append(previous_output)
            for empty_bucket in range(current_bucket + 1, bucket):
                if previous_output is not None:
                    previous_output = make_row(previous_output, bucket_end_ts(empty_bucket, interval_ns))  # type: ignore[arg-type]
                    result.append(previous_output)
        current_bucket = bucket
        current_item = item

    if current_bucket is not None and current_item is not None:
        result.append(make_row(current_item, bucket_end_ts(current_bucket, interval_ns)))
    return result

