"""Build an isolated, post-registration discovery supplement from the catalog."""

from __future__ import annotations

from datetime import UTC
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
from pathlib import Path

from evolution.dataset import DatasetManifest
from evolution.dataset import build_window_from_catalog
from evolution.spec import EXECUTABLE_DISCOVERY_PROFILE
from evolution.spec import INSTRUMENT_IDS
from evolution.spec import Window


PROTECTED_START = datetime(2026, 7, 12, tzinfo=UTC)
PROTECTED_END = datetime(2026, 7, 25, tzinfo=UTC)
QUARANTINED_DAY_START = datetime(2026, 8, 28, tzinfo=UTC)
QUARANTINED_DAY_END = QUARANTINED_DAY_START + timedelta(days=1)


def parse_utc_day(value: str, option_name: str) -> datetime:
    """Parse a UTC-midnight CLI value, accepting YYYY-MM-DD or an ISO timestamp."""
    try:
        if len(value) == 10:
            parsed = datetime.combine(date.fromisoformat(value), time.min, tzinfo=UTC)
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{option_name} must be a UTC day (YYYY-MM-DD or ISO-8601)") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{option_name} must include a timezone")
    parsed = parsed.astimezone(UTC)
    if parsed.time() != time.min:
        raise ValueError(f"{option_name} must be a UTC day at 00:00:00 UTC")
    return parsed


def supplemental_split_name(start: datetime, end: datetime) -> str:
    return f"discovery_supplemental_{start:%Y%m%d}_{end:%Y%m%d}"


def _validate_supplemental_dates(
    instrument_id: str,
    start: datetime,
    end: datetime,
    *,
    now: datetime | None = None,
) -> Window:
    """Validate supplement dates without touching the filesystem or catalog."""
    if instrument_id not in INSTRUMENT_IDS:
        raise ValueError(f"unsupported instrument: {instrument_id}")
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("supplemental window timestamps must include a timezone")
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    if start.time() != time.min or end.time() != time.min:
        raise ValueError("supplemental window must use UTC day boundaries")
    if start >= end:
        raise ValueError("supplemental window start must precede end")
    current_day = (now or datetime.now(UTC)).astimezone(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    if end > current_day:
        raise ValueError("supplemental window must end on a completed UTC day")
    if start < PROTECTED_END and end > PROTECTED_START:
        raise ValueError("supplemental window overlaps protected validation/holdout dates")
    if start < QUARANTINED_DAY_END and end > QUARANTINED_DAY_START:
        raise ValueError("supplemental window overlaps quarantined UTC day 2026-08-28")

    split = supplemental_split_name(start, end)
    if split in {"discovery_1", "discovery_2", "discovery_3", "discovery_4", "discovery_5"}:
        raise ValueError(f"supplemental split name is reserved: {split}")
    return Window(
        split,
        start,
        end,
        EXECUTABLE_DISCOVERY_PROFILE.quote_interval_seconds,
        EXECUTABLE_DISCOVERY_PROFILE.execution_delay_seconds,
    )


def validate_supplemental_window(
    instrument_id: str,
    start: datetime,
    end: datetime,
    output_root: Path,
    *,
    now: datetime | None = None,
) -> Window:
    """Validate a closed-day supplement before any catalog access or writes."""
    window = _validate_supplemental_dates(instrument_id, start, end, now=now)
    target = output_root / window.name / instrument_id
    if target.exists():
        raise RuntimeError(f"supplemental target already exists: {target}")
    return window


def validate_supplemental_audit(
    instrument_id: str,
    split: str,
    start: datetime,
    end: datetime,
    *,
    now: datetime | None = None,
) -> Window:
    """Validate an existing supplement before its local loader is called."""
    expected = _validate_supplemental_dates(instrument_id, start, end, now=now)
    if split != expected.name:
        raise ValueError(
            f"supplemental split name does not match UTC bounds: expected {expected.name}, got {split}",
        )
    return expected


def build_supplemental_discovery(
    instrument_id: str,
    start: datetime,
    end: datetime,
    output_root: Path,
    *,
    now: datetime | None = None,
) -> DatasetManifest:
    """Build one isolated executable-profile supplement using the read-only builder."""
    window = validate_supplemental_window(
        instrument_id, start, end, output_root, now=now,
    )
    return build_window_from_catalog(
        instrument_id,
        window,
        output_root,
        profile=EXECUTABLE_DISCOVERY_PROFILE,
    )


__all__ = [
    "build_supplemental_discovery",
    "parse_utc_day",
    "supplemental_split_name",
    "validate_supplemental_audit",
    "validate_supplemental_window",
]
