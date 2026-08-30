from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from enum import StrEnum
from pathlib import Path


INSTRUMENT_IDS = (
    "BTCUSDT.BINANCE",
    "ETHUSDT.BINANCE",
    "BNBUSDT.BINANCE",
)
SCHEMA_VERSION = 2
STARTING_BALANCE_USDT = 100_000
POSITION_NOTIONAL_USDT = 10_000
FEE_RATE = 0.001


@dataclass(frozen=True)
class ExecutionProfile:
    name: str
    quote_interval_seconds: int
    execution_delay_seconds: int

    def __post_init__(self) -> None:
        if self.quote_interval_seconds <= 0 or self.execution_delay_seconds < 0:
            raise ValueError("invalid execution profile")


FAST_DISCOVERY_PROFILE = ExecutionProfile("fast", 60, 0)
EXECUTABLE_DISCOVERY_PROFILE = ExecutionProfile("executable", 1, 1)


class ResearchStatus(StrEnum):
    INFRASTRUCTURE_ONLY = "infrastructure_only"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"
    FEATURE_CANDIDATE = "feature_candidate"
    RULE_CANDIDATE = "rule_candidate"
    ACCEPTED_ALPHA = "accepted_alpha"


def utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("split timestamps must include a timezone")
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class Window:
    name: str
    start: datetime
    end: datetime
    quote_interval_seconds: int
    execution_delay_seconds: int

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError("window start must precede end")


DISCOVERY_FOLDS = (
    Window("discovery_1", utc("2026-06-13T00:00:00Z"), utc("2026-06-20T00:00:00Z"), 60, 0),
    Window("discovery_2", utc("2026-06-20T00:00:00Z"), utc("2026-06-25T00:00:00Z"), 60, 0),
    Window("discovery_3", utc("2026-06-25T00:00:00Z"), utc("2026-06-30T00:00:00Z"), 60, 0),
    Window("discovery_4", utc("2026-06-30T00:00:00Z"), utc("2026-07-07T00:00:00Z"), 60, 0),
    Window("discovery_5", utc("2026-07-07T00:00:00Z"), utc("2026-07-12T00:00:00Z"), 60, 0),
)
VALIDATION = Window(
    "validation",
    utc("2026-07-12T00:00:00Z"),
    utc("2026-07-18T00:00:00Z"),
    1,
    1,
)
HOLDOUT = Window(
    "holdout",
    utc("2026-07-18T00:00:00Z"),
    utc("2026-07-25T00:00:00Z"),
    1,
    1,
)
ALL_WINDOWS = (*DISCOVERY_FOLDS, VALIDATION, HOLDOUT)


def validate_splits() -> None:
    ordered = sorted(ALL_WINDOWS, key=lambda window: window.start)
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if previous.end > current.start:
            raise ValueError(f"overlapping windows: {previous.name} and {current.name}")


def instrument_slug(instrument_id: str) -> str:
    if instrument_id not in INSTRUMENT_IDS:
        raise ValueError(f"unsupported instrument: {instrument_id}")
    return instrument_id.split(".", 1)[0].lower()


def run_directory(root: Path, instrument_id: str, run_id: str) -> Path:
    if not run_id or Path(run_id).name != run_id:
        raise ValueError("run_id must be one path component")
    return root / instrument_slug(instrument_id) / run_id


validate_splits()
