from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from typing import Iterable
from typing import TypeVar

from common.time_series import NS_PER_SECOND


T = TypeVar("T")


@dataclass(frozen=True)
class PriceKbar:
    start_time: int
    end_time: int
    instrument_id: str
    open: float
    high: float
    low: float
    close: float

    @property
    def ts_event(self) -> int:
        return self.end_time


def aggregate_price_kbars(
    price_points: Iterable[T],
    interval_seconds: int,
    ts_event: Callable[[T], int],
    instrument_id: Callable[[T], str],
    price: Callable[[T], float],
) -> list[PriceKbar]:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")

    interval_ns = interval_seconds * NS_PER_SECOND
    sorted_points = sorted(
        enumerate(price_points),
        key=lambda item: (instrument_id(item[1]), ts_event(item[1]), item[0]),
    )
    if not sorted_points:
        return []

    bars: list[PriceKbar] = []
    current_instrument: str | None = None
    current_bucket: int | None = None
    current_prices: list[float] = []

    for _, point in sorted_points:
        point_instrument = instrument_id(point)
        point_bucket = ts_event(point) // interval_ns
        if (
            current_instrument is not None
            and current_bucket is not None
            and (point_instrument != current_instrument or point_bucket != current_bucket)
        ):
            bars.append(_price_kbar(current_instrument, current_bucket, interval_ns, current_prices))
            current_prices = []

        current_instrument = point_instrument
        current_bucket = point_bucket
        current_prices.append(price(point))

    if current_instrument is not None and current_bucket is not None and current_prices:
        bars.append(_price_kbar(current_instrument, current_bucket, interval_ns, current_prices))

    return sorted(bars, key=lambda bar: (bar.end_time, bar.instrument_id))


def _price_kbar(
    instrument_id: str,
    bucket: int,
    interval_ns: int,
    prices: list[float],
) -> PriceKbar:
    start_time = bucket * interval_ns
    end_time = start_time + interval_ns
    return PriceKbar(
        start_time=start_time,
        end_time=end_time,
        instrument_id=instrument_id,
        open=prices[0],
        high=max(prices),
        low=min(prices),
        close=prices[-1],
    )
