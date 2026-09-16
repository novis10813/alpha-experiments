"""Offline discovery-dataset coverage diagnostics.

This module deliberately reads only the five chronological discovery folds from
local Nautilus catalogs.  It does not build data, access the remote catalog, or
participate in candidate fitness or promotion decisions.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from collections import defaultdict
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Callable
from typing import Iterable


from evolution.dataset import verify_manifest
from evolution.diagnostic import discovery_split
from evolution.market_state import EvolutionMarketState
from evolution.sandbox_worker import load_split
from evolution.spec import DISCOVERY_FOLDS
from evolution.spec import EXECUTABLE_DISCOVERY_PROFILE
from evolution.supplemental import validate_supplemental_audit


NS_PER_MINUTE = 60_000_000_000
LABEL_HORIZONS_MINUTES = (15, 30, 60)
FEATURE_FIELDS = tuple(
    name for name in EvolutionMarketState.FIELDS
    if name not in {"instrument_id", "ts_event", "ts_init"}
)

SplitLoader = Callable[[Path, str], tuple[list[object], list[object], list[object]]]

# These are the lookbacks used by the persisted, past-only state features.  The
# audit reports local window sufficiency separately because a finite neutral
# value does not prove that its historical warmup was available.
FEATURE_LOOKBACKS = {
    "return_5m": 5,
    "return_15m": 15,
    "return_60m": 60,
    "realized_volatility_15m": 15,
    "relative_volume_15m": 15,
    "relative_trade_density_15m": 15,
    "signed_flow_persistence_5m": 4,
    "obi_change_5m": 5,
    "relative_spread_15m": 15,
}
PAST_DISTRIBUTION_FIELDS = (
    "return_5m",
    "return_15m",
    "return_60m",
    "realized_volatility_15m",
    "spread_bps",
    "relative_volume_15m",
    "relative_trade_density_15m",
)


def build_discovery_coverage_report(
    instrument_id: str,
    dataset_root: Path,
    *,
    split_loader: SplitLoader = load_split,
) -> dict[str, object]:
    """Return a deterministic, discovery-only coverage report.

    ``split_loader`` is injectable so the timestamp and feature checks can be
    tested with synthetic Nautilus-like objects without touching a catalog.
    The default loader is the existing local Nautilus catalog loader.
    """
    folds: list[dict[str, object]] = []
    for window in DISCOVERY_FOLDS:
        try:
            split_root, manifest = discovery_split(dataset_root, window.name, instrument_id)
            states, quotes, _bars = split_loader(split_root, instrument_id)
            folds.append(build_fold_coverage_report(window, manifest, states, quotes=quotes))
        except Exception as exc:
            folds.append(
                {
                    "split": window.name,
                    "manifest": None,
                    "manifest_identity": None,
                    "execution_profile": None,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )

    return {
        "instrument_id": instrument_id,
        "discovery_only": True,
        "splits": [window.name for window in DISCOVERY_FOLDS],
        "horizons_minutes": list(LABEL_HORIZONS_MINUTES),
        "folds": folds,
    }


def build_supplemental_coverage_report(
    instrument_id: str,
    split: str,
    start: datetime,
    end: datetime,
    dataset_root: Path,
    *,
    split_loader: SplitLoader = load_split,
    now: datetime | None = None,
) -> dict[str, object]:
    """Audit one existing executable-profile supplement, discovery only.

    Date and split guards, then manifest schema/hash/profile verification, all
    happen before the injectable loader is called.  This command never maps a
    supplemental split into the evaluator's fixed fold set.
    """
    window = validate_supplemental_audit(
        instrument_id, split, start, end, now=now,
    )
    split_root = dataset_root / window.name / instrument_id
    manifest = verify_manifest(
        split_root / "manifest.json",
        instrument_id,
        window.name,
        EXECUTABLE_DISCOVERY_PROFILE.name,
    )
    if (
        manifest.quote_interval_seconds != EXECUTABLE_DISCOVERY_PROFILE.quote_interval_seconds
        or manifest.execution_delay_seconds != EXECUTABLE_DISCOVERY_PROFILE.execution_delay_seconds
    ):
        raise ValueError("dataset manifest executable profile parameters do not match request")
    manifest_start = _parse_manifest_datetime(manifest.source_start)
    manifest_end = _parse_manifest_datetime(manifest.source_end)
    if manifest_start != window.start or manifest_end != window.end:
        raise ValueError("dataset manifest UTC bounds do not match requested supplemental split")
    states, quotes, _bars = split_loader(split_root, instrument_id)
    return {
        "instrument_id": instrument_id,
        "discovery_only": True,
        "supplemental_only": True,
        "split": split,
        "fold": build_fold_coverage_report(window, manifest, states, quotes=quotes),
    }


def run_supplemental_coverage_audit(
    instrument_id: str,
    split: str,
    start: datetime,
    end: datetime,
    dataset_root: Path,
    output_path: Path | None = None,
    *,
    split_loader: SplitLoader = load_split,
    now: datetime | None = None,
) -> dict[str, object]:
    """Audit an existing supplement and optionally write its local report."""
    report = build_supplemental_coverage_report(
        instrument_id,
        split,
        start,
        end,
        dataset_root,
        split_loader=split_loader,
        now=now,
    )
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def run_discovery_coverage_diagnostic(
    instrument_id: str,
    dataset_root: Path,
    output_path: Path | None = None,
    *,
    split_loader: SplitLoader = load_split,
) -> dict[str, object]:
    """Build and optionally write a local discovery coverage report."""
    report = build_discovery_coverage_report(
        instrument_id,
        dataset_root,
        split_loader=split_loader,
    )
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def build_fold_coverage_report(
    window,
    manifest,
    states: Iterable[object],
    quotes: Iterable[object] | None = None,
) -> dict[str, object]:
    """Build the common coverage payload for a verified local split.

    The helper is public so an explicitly named supplemental split can reuse
    the same checks without being added to the fixed evaluator folds.
    """
    return _fold_report(window, manifest, states, quotes=quotes)


def _fold_report(
    window,
    manifest,
    states: Iterable[object],
    quotes: Iterable[object] | None = None,
) -> dict[str, object]:
    state_list = list(states)
    quote_list = list(quotes) if quotes is not None else None
    manifest_payload = asdict(manifest)
    valid_entries, invalid_timestamps = _timestamp_entries(state_list)
    in_window = [
        (timestamp, state, index)
        for timestamp, state, index in valid_entries
        if _in_window(timestamp, window)
    ]
    continuity = _continuity_report(window, valid_entries, invalid_timestamps)
    labels = _label_report(
        window,
        in_window,
        continuity["present_timestamps"],
        continuity["expected_timestamps"],
        state_list,
    )
    features = _feature_report(in_window, window=window)
    distributions = _past_state_distributions(in_window, window)
    quote_quality = (
        _quote_quality_report(
            quote_list,
            window,
            manifest.instrument_id,
            manifest.quote_interval_seconds,
        )
        if quote_list is not None else None
    )
    continuity.pop("present_timestamps")
    continuity.pop("expected_timestamps")

    manifest_checks = _manifest_checks(
        window,
        manifest,
        len(state_list),
        continuity["expected_bucket_count"],
        observed_quote_count=len(quote_list) if quote_list is not None else None,
    )
    return {
        "split": window.name,
        "error": None,
        "manifest": manifest_payload,
        "manifest_identity": {
            "schema_version": manifest.schema_version,
            "instrument_id": manifest.instrument_id,
            "split": manifest.split,
            "source_start": manifest.source_start,
            "source_end": manifest.source_end,
            "files": dict(sorted(manifest.files.items())),
        },
        "execution_profile": {
            "name": manifest.execution_profile,
            "quote_interval_seconds": manifest.quote_interval_seconds,
            "execution_delay_seconds": manifest.execution_delay_seconds,
        },
        "manifest_checks": manifest_checks,
        "state_timestamps": continuity,
        "label_availability": labels,
        "feature_readiness": features,
        "past_state_distributions": distributions,
        "quote_quality": quote_quality,
    }


def _timestamp_entries(states: list[object]):
    valid: list[tuple[int, object, int]] = []
    invalid: list[dict[str, object]] = []
    for index, state in enumerate(states):
        value = getattr(state, "ts_event", None)
        try:
            if value is None or isinstance(value, bool):
                raise ValueError("missing timestamp" if value is None else "boolean timestamp")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("non-finite timestamp")
            timestamp = int(value)
            if timestamp != value:
                raise ValueError("timestamp is not an integer")
            if timestamp < 0:
                raise ValueError("timestamp is negative")
        except (TypeError, ValueError, OverflowError):
            invalid.append(
                {
                    "index": index,
                    "value": repr(value)[:120],
                    "reason": _timestamp_error(value),
                },
            )
            continue
        valid.append((timestamp, state, index))
    return valid, invalid


def _timestamp_error(value: object) -> str:
    if value is None:
        return "missing timestamp"
    if isinstance(value, bool):
        return "boolean timestamp"
    try:
        if isinstance(value, float) and not math.isfinite(value):
            return "non-finite timestamp"
        if int(value) != value:
            return "timestamp is not an integer"
        if int(value) < 0:
            return "timestamp is negative"
    except (TypeError, ValueError, OverflowError):
        pass
    return "invalid timestamp"


def _in_window(timestamp: int, window) -> bool:
    start = _datetime_to_ns(window.start)
    end = _datetime_to_ns(window.end)
    return start < timestamp <= end


def _continuity_report(window, entries, invalid_timestamps):
    start = _datetime_to_ns(window.start)
    end = _datetime_to_ns(window.end)
    expected = list(range(start + NS_PER_MINUTE, end + 1, NS_PER_MINUTE))
    expected_set = set(expected)
    in_window_times = [timestamp for timestamp, _state, _index in entries if timestamp in expected_set]
    present = set(in_window_times)
    missing = sorted(expected_set - present)
    unexpected = sorted(
        timestamp for timestamp, _state, _index in entries
        if start < timestamp <= end and timestamp not in expected_set
    )
    duplicate_count = len(in_window_times) - len(present)
    transitions = []
    unique_times = sorted(present)
    for previous, current in zip(unique_times, unique_times[1:], strict=False):
        if current - previous != NS_PER_MINUTE:
            transitions.append(
                {
                    "from_ts_event": previous,
                    "to_ts_event": current,
                    "delta_seconds": (current - previous) / 1_000_000_000,
                },
            )
    return {
        "expected_interval_seconds": 60,
        "expected_bucket_count": len(expected),
        "observed_valid_count": len(entries),
        "observed_in_window_count": len(in_window_times),
        "first_ts_event": min(in_window_times, default=None),
        "last_ts_event": max(in_window_times, default=None),
        "invalid_timestamp_count": len(invalid_timestamps),
        "invalid_timestamps": invalid_timestamps,
        "duplicate_timestamp_count": duplicate_count,
        "unexpected_timestamp_count": len(unexpected),
        "unexpected_timestamps": unexpected,
        "missing_bucket_count": len(missing),
        "gaps": _compress_timestamps(missing),
        "non_contiguous_transitions": transitions,
        "continuous": not invalid_timestamps and not missing and not unexpected and not duplicate_count,
        "present_timestamps": present,
        "expected_timestamps": expected_set,
    }


def _compress_timestamps(timestamps: list[int]) -> list[dict[str, object]]:
    if not timestamps:
        return []
    ranges: list[dict[str, object]] = []
    start = previous = timestamps[0]
    for timestamp in timestamps[1:]:
        if timestamp - previous != NS_PER_MINUTE:
            ranges.append(_timestamp_range(start, previous))
            start = timestamp
        previous = timestamp
    ranges.append(_timestamp_range(start, previous))
    return ranges


def _timestamp_range(start: int, end: int) -> dict[str, object]:
    return {
        "start_ts_event": start,
        "end_ts_event": end,
        "missing_bucket_count": (end - start) // NS_PER_MINUTE + 1,
    }


def _label_report(
    window,
    in_window,
    present_timestamps: set[int],
    expected_timestamps: set[int],
    all_states: list[object],
):
    by_timestamp: dict[int, list[object]] = {}
    for timestamp, state, _index in in_window:
        by_timestamp.setdefault(timestamp, []).append(state)
    labels: dict[str, object] = {}
    candidates = [
        entry for entry in in_window
        if entry[0] in expected_timestamps
    ]
    for horizon_minutes in LABEL_HORIZONS_MINUTES:
        horizon_ns = horizon_minutes * NS_PER_MINUTE
        available = 0
        reasons: dict[str, int] = {}
        for timestamp, state, _index in candidates:
            reason = _label_unavailable_reason(
                timestamp,
                state,
                horizon_ns,
                window,
                by_timestamp,
                present_timestamps,
                all_states,
            )
            if reason is None:
                available += 1
            else:
                reasons[reason] = reasons.get(reason, 0) + 1
        candidate_count = len(candidates)
        labels[str(horizon_minutes)] = {
            "horizon_minutes": horizon_minutes,
            "candidate_count": candidate_count,
            "available_count": available,
            "unavailable_count": candidate_count - available,
            "availability_ratio": available / candidate_count if candidate_count else None,
            "unavailable_reasons": dict(sorted(reasons.items())),
        }
    return labels


def _label_unavailable_reason(
    timestamp,
    state,
    horizon_ns,
    window,
    by_timestamp,
    present_timestamps,
    all_states,
):
    if len(by_timestamp[timestamp]) != 1:
        return "duplicate_timestamp"
    if not _finite_number(getattr(state, "close", None)):
        return "nonfinite_close"
    target = timestamp + horizon_ns
    if target > _datetime_to_ns(window.end):
        return "horizon_out_of_window"
    target_states = by_timestamp.get(target)
    if not target_states:
        if any(
            getattr(candidate, "ts_event", None) == target
            for candidate in all_states
        ):
            return "target_out_of_window"
        return "missing_target"
    if len(target_states) != 1:
        return "duplicate_target_timestamp"
    if not _finite_number(getattr(target_states[0], "close", None)):
        return "nonfinite_target_close"
    for current in range(timestamp + NS_PER_MINUTE, target + 1, NS_PER_MINUTE):
        if current not in present_timestamps:
            return "gap"
    return None


def _feature_report(in_window, *, window=None):
    row_count = len(in_window)
    fields: dict[str, object] = {}
    warmup = _warmup_report(in_window) if window is not None else {}
    for name in FEATURE_FIELDS:
        missing = 0
        nonfinite = 0
        for _timestamp, state, _index in in_window:
            value = getattr(state, name, None)
            if value is None:
                missing += 1
            elif not _finite_number(value):
                nonfinite += 1
        finite_ready = row_count > 0 and missing == 0 and nonfinite == 0
        field = {
            "finite_count": row_count - missing - nonfinite,
            "missing_count": missing,
            "nonfinite_count": nonfinite,
            # Kept for compatibility: this means finite persisted values only.
            "ready": finite_ready,
            "finite_ready": finite_ready,
            "incomplete_warmup_count": warmup.get(name),
            "warmup_sufficiency": "not_proven",
        }
        fields[name] = field
    ready = row_count > 0 and all(field["finite_ready"] for field in fields.values())
    return {
        "row_count": row_count,
        "ready": ready,
        "finite_ready": ready,
        "warmup_sufficiency": {
            "status": "not_proven",
            "reason": "finite feature values do not prove historical warmup was available",
        },
        "fields": fields,
    }


def _warmup_report(in_window) -> dict[str, int | None]:
    if not in_window:
        return {name: 0 for name in FEATURE_FIELDS}
    entries = sorted(in_window, key=lambda item: item[0])
    contiguous_prior = 0
    previous_timestamp: int | None = None
    incomplete: dict[str, int] = {name: 0 for name in FEATURE_FIELDS}
    for timestamp, _state, _index in entries:
        if previous_timestamp is None or timestamp - previous_timestamp != NS_PER_MINUTE:
            contiguous_prior = 0
        for name, required in FEATURE_LOOKBACKS.items():
            if contiguous_prior < required:
                incomplete[name] += 1
        previous_timestamp = timestamp
        contiguous_prior += 1
    return incomplete


def _past_state_distributions(in_window, window) -> dict[str, object]:
    by_day: dict[str, list[tuple[int, object]]] = defaultdict(list)
    for timestamp, state, _index in in_window:
        day = datetime.fromtimestamp(timestamp / 1_000_000_000, tz=UTC).date().isoformat()
        by_day[day].append((timestamp, state))

    result: dict[str, object] = {}
    for day, entries in sorted(by_day.items()):
        result[day] = {
            "state_count": len(entries),
            "fields": {
                name: _distribution(
                    [getattr(state, name, None) for _timestamp, state in entries],
                    undefined_denominator_count=_undefined_denominators(in_window, day, name),
                    incomplete_warmup_count=_day_incomplete_warmup(in_window, day, name),
                )
                for name in PAST_DISTRIBUTION_FIELDS
            },
            "price_path_efficiency_60m": _price_efficiency_distribution(in_window, day),
        }
    return {
        "utc_day_basis": "state ts_event in UTC",
        "fields": list(PAST_DISTRIBUTION_FIELDS),
        "days": result,
    }


def _distribution(
    values,
    *,
    undefined_denominator_count: int | None = None,
    incomplete_warmup_count: int = 0,
) -> dict[str, object]:
    finite = [float(value) for value in values if _finite_number(value)]
    missing_count = sum(value is None for value in values)
    nonfinite_count = len(values) - missing_count - len(finite)
    ordered = sorted(finite)
    return {
        "sample_count": len(values),
        "finite_count": len(finite),
        "missing_count": missing_count,
        "nonfinite_count": nonfinite_count,
        "minimum": ordered[0] if ordered else None,
        "p10": _percentile(ordered, 0.10),
        "median": _percentile(ordered, 0.50),
        "mean": sum(finite) / len(finite) if finite else None,
        "p90": _percentile(ordered, 0.90),
        "maximum": ordered[-1] if ordered else None,
        "undefined_denominator_count": undefined_denominator_count,
        "incomplete_warmup_count": incomplete_warmup_count,
    }


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _day_incomplete_warmup(in_window, day: str, name: str) -> int:
    entries = sorted(in_window, key=lambda item: item[0])
    required = FEATURE_LOOKBACKS.get(name, 0)
    prior = 0
    previous: int | None = None
    count = 0
    for timestamp, _state, _index in entries:
        current_day = datetime.fromtimestamp(timestamp / 1_000_000_000, tz=UTC).date().isoformat()
        if previous is None or timestamp - previous != NS_PER_MINUTE:
            prior = 0
        if current_day == day and prior < required:
            count += 1
        previous = timestamp
        prior += 1
    return count


def _undefined_denominators(all_entries, day: str, name: str) -> int | None:
    # These denominators are recoverable from the state inputs.  Neutralized
    # values alone cannot reveal whether a denominator was undefined.
    if name not in {"return_5m", "return_15m", "return_60m", "relative_volume_15m", "relative_trade_density_15m", "relative_spread_15m"}:
        return 0
    states = sorted(all_entries, key=lambda item: item[0])
    required = FEATURE_LOOKBACKS[name]
    count = 0
    for index, (timestamp, state, _row_index) in enumerate(states):
        current_day = datetime.fromtimestamp(timestamp / 1_000_000_000, tz=UTC).date().isoformat()
        if current_day != day or index < required or states[index - required][0] != timestamp - required * NS_PER_MINUTE:
            continue
        if name.startswith("return_"):
            denominator = getattr(states[index - required][1], "close", None)
        else:
            attribute = {
                "relative_volume_15m": "volume",
                "relative_trade_density_15m": "trade_count",
                "relative_spread_15m": "spread_bps",
            }[name]
            denominator = sum(
                float(getattr(states[item_index][1], attribute, 0.0))
                for item_index in range(index - required, index)
            )
        if not _finite_number(denominator) or denominator == 0:
            count += 1
    return count


def _price_efficiency_distribution(in_window, day: str) -> dict[str, object]:
    entries = sorted(in_window, key=lambda item: item[0])
    values: list[float] = []
    incomplete = 0
    undefined = 0
    nonfinite = 0
    for index, (timestamp, state, _row_index) in enumerate(entries):
        current_day = datetime.fromtimestamp(timestamp / 1_000_000_000, tz=UTC).date().isoformat()
        if current_day != day:
            continue
        if index < 60 or any(
            entries[item][0] != timestamp - (index - item) * NS_PER_MINUTE
            for item in range(index - 60, index)
        ):
            incomplete += 1
            continue
        closes = [getattr(entries[item][1], "close", None) for item in range(index - 60, index + 1)]
        if any(not _finite_number(value) for value in closes):
            nonfinite += 1
            continue
        denominator = sum(abs(float(closes[item]) - float(closes[item - 1])) for item in range(1, len(closes)))
        if denominator == 0:
            undefined += 1
            continue
        values.append(abs(float(closes[-1]) - float(closes[0])) / denominator)
    return {
        "window_minutes": 60,
        "definition": "abs(net change) / sum(abs(one-minute changes))",
        **_distribution(
            values,
            undefined_denominator_count=undefined,
            incomplete_warmup_count=incomplete,
        ),
        "nonfinite_window_count": nonfinite,
    }


def _quote_quality_report(
    quotes: list[object],
    window,
    instrument_id: str,
    interval_seconds: int = 1,
) -> dict[str, object]:
    start = _datetime_to_ns(window.start)
    end = _datetime_to_ns(window.end)
    interval_ns = interval_seconds * 1_000_000_000
    # Quotes are completed interval states: the valid grid is (start, end].
    expected = set(range(start + interval_ns, end + 1, interval_ns))
    timestamps: list[int] = []
    invalid_timestamp_count = 0
    nonfinite_count = 0
    crossed_count = 0
    boundary_count = 0
    alignment_count = 0
    instrument_mismatch_count = 0
    for quote in quotes:
        timestamp = getattr(quote, "ts_event", None)
        try:
            if isinstance(timestamp, bool) or not _finite_number(timestamp) or int(timestamp) != timestamp:
                raise ValueError
            timestamp = int(timestamp)
        except (TypeError, ValueError, OverflowError):
            invalid_timestamp_count += 1
            timestamp = None
        if timestamp is not None:
            timestamps.append(timestamp)
            if timestamp <= start or timestamp > end:
                boundary_count += 1
            elif (timestamp - start) % interval_ns:
                alignment_count += 1
        if str(getattr(quote, "instrument_id", "")) != instrument_id:
            instrument_mismatch_count += 1
        numeric = [getattr(quote, name, None) for name in ("bid", "ask", "mid", "spread", "spread_bps")]
        if any(not _finite_number(value) for value in numeric):
            nonfinite_count += 1
        elif float(quote.bid) > float(quote.ask):
            crossed_count += 1
    present = set(timestamps) & expected
    duplicate_count = len(timestamps) - len(set(timestamps))
    missing = sorted(expected - present)
    return {
        "count": len(quotes),
        "duplicate_timestamp_count": duplicate_count,
        "missing_second_count": len(missing),
        "missing_seconds": _compress_seconds(missing),
        "crossed_count": crossed_count,
        "instrument_mismatch_count": instrument_mismatch_count,
        "nonfinite_count": nonfinite_count,
        "invalid_timestamp_count": invalid_timestamp_count,
        "boundary_violation_count": boundary_count,
        "timestamp_alignment_violation_count": alignment_count,
        "expected_interval_seconds": interval_seconds,
        "expected_sample_count": len(expected),
        "in_window_unique_sample_count": len(present),
        "continuous": not any((duplicate_count, len(missing), crossed_count, instrument_mismatch_count, nonfinite_count, invalid_timestamp_count, boundary_count, alignment_count)),
    }


def _compress_seconds(timestamps: list[int]) -> list[dict[str, object]]:
    if not timestamps:
        return []
    ranges = []
    start = previous = timestamps[0]
    for timestamp in timestamps[1:]:
        if timestamp - previous != 1_000_000_000:
            ranges.append({"start_ts_event": start, "end_ts_event": previous, "missing_second_count": (previous - start) // 1_000_000_000 + 1})
            start = timestamp
        previous = timestamp
    ranges.append({"start_ts_event": start, "end_ts_event": previous, "missing_second_count": (previous - start) // 1_000_000_000 + 1})
    return ranges


def _finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _manifest_checks(
    window,
    manifest,
    observed_row_count: int,
    expected_bucket_count: int,
    observed_quote_count: int | None = None,
) -> dict[str, object]:
    issues: list[str] = []
    start = _parse_manifest_datetime(manifest.source_start)
    end = _parse_manifest_datetime(manifest.source_end)
    if start is None:
        issues.append("invalid source_start")
    if end is None:
        issues.append("invalid source_end")
    if start is not None and start != window.start:
        issues.append("source_start does not match discovery window")
    if end is not None and end != window.end:
        issues.append("source_end does not match discovery window")
    row_count_matches = manifest.row_count == observed_row_count
    missing_count_matches = manifest.missing_bucket_count == max(
        0,
        expected_bucket_count - observed_row_count,
    )
    if not row_count_matches:
        issues.append("manifest row_count does not match observed state count")
    if not missing_count_matches:
        issues.append("manifest missing_bucket_count does not match observed state count")
    quote_count_matches = None
    if observed_quote_count is not None:
        quote_count_matches = manifest.quote_count == observed_quote_count
        if not quote_count_matches:
            issues.append("manifest quote_count does not match observed quote count")
    return {
        "source_start_valid": start is not None,
        "source_end_valid": end is not None,
        "source_window_matches": start == window.start and end == window.end,
        "row_count_matches_observed": row_count_matches,
        "missing_bucket_count_matches_observed": missing_count_matches,
        "quote_count_matches_observed": quote_count_matches,
        "issues": issues,
    }


def _parse_manifest_datetime(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _datetime_to_ns(value: datetime) -> int:
    utc_value = value.astimezone(UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = utc_value - epoch
    return (
        (delta.days * 86_400 + delta.seconds) * 1_000_000_000
        + delta.microseconds * 1_000
    )


__all__ = [
    "FEATURE_FIELDS",
    "LABEL_HORIZONS_MINUTES",
    "build_discovery_coverage_report",
    "build_fold_coverage_report",
    "build_supplemental_coverage_report",
    "run_discovery_coverage_diagnostic",
    "run_supplemental_coverage_audit",
]
