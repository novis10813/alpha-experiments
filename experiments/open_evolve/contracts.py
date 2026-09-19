"""Value-only policy interface. These types are not a Python security sandbox."""

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class TargetPosition(Enum):
    FLAT = 0
    LONG = 1
    SHORT = -1


@dataclass(frozen=True, slots=True)
class MarketState:
    """No engine references, history arrays, absolute timestamps, or fold IDs."""

    ready: bool
    book_valid: bool
    book_age_ns: int | None
    trade_age_ns: int | None
    mid: float | None
    spread_bps: float | None
    microprice_offset_bps: float | None
    book_imbalance: float | None
    ofi: float | None
    trade_imbalance: float | None
    known_trade_fraction: float | None
    log_return: float | None
    realized_volatility: float | None
    one_sidedness_age_ns: int | None
    ofi_accel: float | None
    trade_size_ratio: float | None
    large_trade_imbalance: float | None
    depth_concentration_bid: float | None
    depth_concentration_ask: float | None
    trade_density: int | None


@dataclass(frozen=True, slots=True)
class PositionState:
    signed_quantity: float
    average_entry_price: float | None
    holding_time_ns: int
    unrealized_return_bps: float | None
    order_pending: bool

    def __post_init__(self) -> None:
        if not isfinite(self.signed_quantity):
            raise ValueError("signed_quantity must be finite")
        if type(self.holding_time_ns) is not int or self.holding_time_ns < 0:
            raise ValueError("holding_time_ns must be a nonnegative integer")
        if type(self.order_pending) is not bool:
            raise ValueError("order_pending must be boolean")
        if self.signed_quantity == 0:
            if (self.average_entry_price is not None
                    or self.unrealized_return_bps is not None
                    or self.holding_time_ns != 0):
                raise ValueError("flat position must not contain holding statistics")
        elif (self.average_entry_price is None
              or not isfinite(self.average_entry_price)
              or self.average_entry_price <= 0):
            raise ValueError("open position needs a positive finite entry price")
        if (self.unrealized_return_bps is not None
                and not isfinite(self.unrealized_return_bps)):
            raise ValueError("unrealized_return_bps must be finite or missing")


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    """Host-only envelope; only ``market`` may be sent to a policy."""

    source_ts_event: int
    source_ts_init: int
    source_sequence: int | None
    available_at: int
    event_ordinal: int
    schema_version: str
    market: MarketState


def validate_target(value: object, *, allow_short: bool) -> TargetPosition:
    """Reject invalid outputs; never silently convert errors to FLAT."""
    if type(value) is not TargetPosition:
        raise ValueError("policy must return a TargetPosition enum")
    if value is TargetPosition.SHORT and not allow_short:
        raise ValueError("SHORT is not allowed by the account contract")
    return value
