"""Fixed-horizon diagnostics for registered declarative family entry rules.

This is a discovery supplement diagnostic, not a strategy backtest.  It evaluates
only the registered seed ``RULE_SPEC`` entry conditions, samples signal times in
chronological order, and then measures fixed forward quote outcomes.
"""

from __future__ import annotations

import hashlib
import json
import math
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Iterable

from data.orderbook_quotes import QuoteRow
from evolution.coverage import _datetime_to_ns
from evolution.coverage import _parse_manifest_datetime
from evolution.dataset import DatasetManifest, verify_manifest
from evolution.families import EvolutionFamily, sha256_file, validate_family_instrument
from evolution.rules import RuleSpec, rule_source_signature, validate_rule_source
from evolution.sandbox_worker import load_split
from evolution.supplemental import validate_supplemental_audit


HORIZONS_MINUTES = (15, 30, 60)
MINUTE_NS = 60_000_000_000
SECOND_NS = 1_000_000_000
WARMUP_MINUTES = 60
EVENT_SPACING_MINUTES = 60
FEE_BPS_EACH_SIDE = 10.0
QUOTE_TOLERANCE_SECONDS = 1

FIXED_SIGNAL_DIAGNOSTIC_SPEC = {
    "diagnostic": "registered_declarative_entry_forward_quotes_v1",
    "horizons_minutes": list(HORIZONS_MINUTES),
    "event_timestamp": "completed EvolutionMarketState.ts_event",
    "entry_conditions": "registered RULE_SPEC entry conditions, all conditions, exact consecutive confirmations",
    "state_order": "chronological finite states; a non-one-minute transition resets confirmations and warmup",
    "warmup": "exclude first 60 minutes and require 60 contiguous prior one-minute states",
    "event_sampling": "chronological, non-overlapping events with 60-minute spacing per family; outcome-independent",
    "entry_execution": "buy ask at first quote timestamp >= event_ts + 1 second",
    "exit_execution": "sell bid at first quote timestamp >= event_ts + horizon + 1 second",
    "quote_tolerance_seconds": QUOTE_TOLERANCE_SECONDS,
    "quote_gap_policy": "reject if the first quote is more than one second late; no interpolation",
    "split_boundary_policy": "reject executions outside (split_start, split_end]",
    "fees_bps_each_side": FEE_BPS_EACH_SIDE,
    "comparison": "the same sampled event timestamps are evaluated at 15, 30, and 60 minutes",
    "purpose": "fixed-horizon diagnostic, not a strategy or full portfolio backtest",
    "significance_testing": "none; no significance or alpha claim",
}

SplitLoader = Callable[[Path, str], tuple[list[object], list[object], list[object]]]


def build_supplemental_signal_diagnostic(
    instrument_id: str,
    family_id: str,
    split: str,
    start: datetime,
    end: datetime,
    dataset_root: Path,
    *,
    split_loader: SplitLoader = load_split,
    now: datetime | None = None,
) -> dict[str, object]:
    """Build a guarded, offline diagnostic from one supplemental split.

    Every family, date, split, manifest, profile, and hash check happens before
    ``split_loader`` is called.  The loader is the existing local Nautilus
    loader; this function never opens a remote catalog.
    """
    family = validate_family_instrument(family_id, instrument_id)
    rule = _registered_rule(family)
    window = validate_supplemental_audit(
        instrument_id, split, start, end, now=now,
    )
    split_root = dataset_root / split / instrument_id
    manifest = verify_manifest(
        split_root / "manifest.json",
        instrument_id,
        split,
        "executable",
    )
    _validate_manifest_bounds(manifest, window)
    if manifest.quote_interval_seconds != 1 or manifest.execution_delay_seconds != 1:
        raise ValueError("supplemental signal diagnostic requires the executable 1-second/1-second profile")

    states, quotes, _bars = split_loader(split_root, instrument_id)
    events, signal_exclusions = collect_entry_events(states, rule, window.start, window.end)
    quote_index = _QuoteIndex(quotes, instrument_id, window.start, window.end)
    event_rows: list[dict[str, object]] = []
    horizon_exclusions: dict[str, Counter[str]] = {str(horizon): Counter() for horizon in HORIZONS_MINUTES}
    for event in events:
        event_payload = {
            "event_ts": event,
            "utc_day": _utc_day(event),
            "horizons": {},
        }
        for horizon in HORIZONS_MINUTES:
            result, reason = _measure_event(quote_index, event, horizon, quote_index.end_ns)
            if reason is not None:
                horizon_exclusions[str(horizon)][reason] += 1
                event_payload["horizons"][str(horizon)] = {"excluded_reason": reason}
            else:
                event_payload["horizons"][str(horizon)] = result
        event_rows.append(event_payload)

    return _report(
        instrument_id=instrument_id,
        family=family,
        rule=rule,
        manifest=manifest,
        event_rows=event_rows,
        signal_exclusions=signal_exclusions,
        horizon_exclusions=horizon_exclusions,
    )


def run_supplemental_signal_diagnostic(
    instrument_id: str,
    family_id: str,
    split: str,
    start: datetime,
    end: datetime,
    dataset_root: Path,
    output_path: Path,
    *,
    split_loader: SplitLoader = load_split,
    now: datetime | None = None,
) -> dict[str, object]:
    report = build_supplemental_signal_diagnostic(
        instrument_id, family_id, split, start, end, dataset_root,
        split_loader=split_loader, now=now,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def collect_entry_events(
    states: Iterable[object],
    rule: RuleSpec,
    start: datetime,
    end: datetime,
) -> tuple[list[int], dict[str, int]]:
    """Apply the rule interpreter's entry confirmation semantics without outcomes."""
    start_ns = _datetime_to_ns(start)
    end_ns = _datetime_to_ns(end)
    warmup_end = start_ns + WARMUP_MINUTES * MINUTE_NS
    valid_states: list[tuple[int, object]] = []
    exclusions: Counter[str] = Counter()
    for state in states:
        timestamp = _safe_timestamp(getattr(state, "ts_event", None))
        if timestamp is None:
            exclusions["invalid_timestamp"] += 1
        elif not start_ns < timestamp <= end_ns:
            exclusions["outside_window"] += 1
        else:
            valid_states.append((timestamp, state))
    valid_states.sort(key=lambda item: item[0])

    confirmations = 0
    contiguous_count = 0
    previous_ts: int | None = None
    sampled: list[int] = []
    seen_timestamps: set[int] = set()
    for timestamp, state in valid_states:
        if timestamp in seen_timestamps:
            exclusions["duplicate_timestamp"] += 1
            confirmations = 0
            contiguous_count = 0
            previous_ts = timestamp
            continue
        seen_timestamps.add(timestamp)
        if not _state_is_finite_for_rule(state, rule):
            exclusions["nonfinite_state"] += 1
            confirmations = 0
            contiguous_count = 0
            previous_ts = timestamp
            continue
        contiguous = previous_ts is not None and timestamp - previous_ts == MINUTE_NS
        if contiguous:
            contiguous_count += 1
        else:
            contiguous_count = 1
            confirmations = 0
        matched = _matches_entry(rule, state)
        confirmations = confirmations + 1 if matched else 0
        if confirmations >= rule.entry.confirmations:
            confirmations = 0
            if timestamp <= warmup_end:
                exclusions["warmup"] += 1
            elif contiguous_count <= WARMUP_MINUTES:
                exclusions["gap_warmup"] += 1
            elif sampled and timestamp - sampled[-1] < EVENT_SPACING_MINUTES * MINUTE_NS:
                exclusions["spacing"] += 1
            else:
                sampled.append(timestamp)
        previous_ts = timestamp
    return sampled, dict(sorted(exclusions.items()))


def _registered_rule(family: EvolutionFamily) -> RuleSpec:
    result = validate_rule_source(family.seed_program)
    if not result.valid or result.spec is None:
        raise ValueError(f"registered family seed is not a valid declarative rule: {family.family_id}")
    if result.spec.family_id != family.family_id:
        raise ValueError("registered family seed family_id does not match registry")
    return result.spec


def _state_is_finite_for_rule(state: object, rule: RuleSpec) -> bool:
    return all(
        _finite_float(getattr(state, condition.feature, None)) is not None
        for condition in rule.entry.conditions
    )


def _matches_entry(rule: RuleSpec, state: object) -> bool:
    for condition in rule.entry.conditions:
        value = getattr(state, condition.feature, None)
        if isinstance(value, bool):
            return False
        try:
            value = float(value)
        except (TypeError, ValueError, OverflowError):
            return False
        if not math.isfinite(value):
            return False
        threshold = float(condition.value)
        if condition.op == "gt" and not value > threshold:
            return False
        if condition.op == "gte" and not value >= threshold:
            return False
        if condition.op == "lt" and not value < threshold:
            return False
        if condition.op == "lte" and not value <= threshold:
            return False
    return True


def _measure_event(
    quotes: "_QuoteIndex",
    event_ts: int,
    horizon_minutes: int,
    split_end_ns: int,
) -> tuple[dict[str, float | int] | None, str | None]:
    scheduled_exit = event_ts + horizon_minutes * MINUTE_NS
    entry_target = event_ts + SECOND_NS
    exit_target = scheduled_exit + SECOND_NS
    if scheduled_exit > split_end_ns or entry_target > split_end_ns or exit_target > split_end_ns:
        return None, "horizon_out_of_window"
    entry, reason = quotes.first_at_or_after(entry_target)
    if reason is not None:
        return None, f"entry_{reason}"
    exit_quote, reason = quotes.first_at_or_after(exit_target)
    if reason is not None:
        return None, f"exit_{reason}"
    assert entry is not None and exit_quote is not None
    if not quotes.continuous_between(entry.ts_event, exit_quote.ts_event):
        return None, "quote_gap"
    gross_bps, net_bps = executable_bps(entry.ask, exit_quote.bid)
    return {
        "event_ts": event_ts,
        "scheduled_exit_ts": scheduled_exit,
        "entry_quote_ts": entry.ts_event,
        "entry_ask": entry.ask,
        "exit_quote_ts": exit_quote.ts_event,
        "exit_bid": exit_quote.bid,
        "gross_bps": gross_bps,
        "net_bps": net_bps,
        "win": int(net_bps > 0),
    }, None


def executable_bps(entry_ask: float, exit_bid: float) -> tuple[float, float]:
    """Return bid/ask gross bps and 10-bps-per-side fee-adjusted bps."""
    if not all(math.isfinite(float(value)) and float(value) > 0 for value in (entry_ask, exit_bid)):
        raise ValueError("execution prices must be finite and positive")
    gross = (float(exit_bid) / float(entry_ask) - 1.0) * 10_000.0
    net = ((float(exit_bid) * (1.0 - FEE_BPS_EACH_SIDE / 10_000.0)) /
           (float(entry_ask) * (1.0 + FEE_BPS_EACH_SIDE / 10_000.0)) - 1.0) * 10_000.0
    return gross, net


class _QuoteIndex:
    def __init__(self, quotes: Iterable[object], instrument_id: str, start: datetime, end: datetime) -> None:
        self.instrument_id = instrument_id
        self.start_ns = _datetime_to_ns(start)
        self.end_ns = _datetime_to_ns(end)
        self.rows = sorted(quotes, key=lambda quote: _safe_timestamp(getattr(quote, "ts_event", None)) or -1)
        self.timestamps = [_safe_timestamp(getattr(quote, "ts_event", None)) or -1 for quote in self.rows]
        self._valid_timestamps = {
            timestamp for timestamp, quote in zip(self.timestamps, self.rows, strict=True)
            if self._valid_quote(timestamp, quote)
        }

    def first_at_or_after(self, target: int) -> tuple[QuoteRow | None, str | None]:
        if target > self.end_ns:
            return None, "split_end"
        index = bisect_left(self.timestamps, target)
        if index >= len(self.rows):
            return None, "quote_gap"
        raw = self.rows[index]
        timestamp = self.timestamps[index]
        if timestamp < self.start_ns or timestamp > self.end_ns:
            return None, "split_end"
        if timestamp - target > QUOTE_TOLERANCE_SECONDS * SECOND_NS:
            return None, "quote_tolerance"
        if str(getattr(raw, "instrument_id", "")) != self.instrument_id:
            return None, "instrument_mismatch"
        bid = _finite_float(getattr(raw, "bid", None))
        ask = _finite_float(getattr(raw, "ask", None))
        if bid is None or ask is None or bid <= 0 or ask <= 0 or bid > ask:
            return None, "invalid_quote"
        return QuoteRow(timestamp, self.instrument_id, bid, ask, (bid + ask) / 2, ask - bid, (ask - bid) / ((bid + ask) / 2) * 10_000), None

    def continuous_between(self, start: int, end: int) -> bool:
        return all(
            timestamp in self._valid_timestamps
            for timestamp in range(start, end + SECOND_NS, SECOND_NS)
        )

    def _valid_quote(self, timestamp: int, quote: object) -> bool:
        if timestamp < self.start_ns or timestamp > self.end_ns:
            return False
        if str(getattr(quote, "instrument_id", "")) != self.instrument_id:
            return False
        bid = _finite_float(getattr(quote, "bid", None))
        ask = _finite_float(getattr(quote, "ask", None))
        return bid is not None and ask is not None and bid > 0 and ask > 0 and bid <= ask


def _report(
    *,
    instrument_id: str,
    family: EvolutionFamily,
    rule: RuleSpec,
    manifest: DatasetManifest,
    event_rows: list[dict[str, object]],
    signal_exclusions: dict[str, int],
    horizon_exclusions: dict[str, Counter[str]],
) -> dict[str, object]:
    by_day: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(lambda: defaultdict(list))
    overall: dict[str, list[dict[str, object]]] = defaultdict(list)
    for event in event_rows:
        day = str(event["utc_day"])
        for horizon in HORIZONS_MINUTES:
            result = event["horizons"][str(horizon)]
            if "net_bps" in result:
                by_day[day][str(horizon)].append(result)
                overall[str(horizon)].append(result)

    preregistration = family.preregistration
    family_material = preregistration.read_bytes() if preregistration.is_file() else family.family_id.encode()
    family_hash = hashlib.sha256(family_material).hexdigest()
    code_hash = sha256_file(family.seed_program)
    rule_hash = rule_source_signature(rule)
    dataset_hash = hashlib.sha256(
        json.dumps(asdict(manifest), sort_keys=True, separators=(",", ":")).encode(),
    ).hexdigest()
    mechanism = (
        "risk_off_long_flat_filter_entry_conditions; no bullish assumption is made"
        if family.family_id == "down-streak-risk-off-btc-v1"
        else "registered_long_entry_condition_event; no strategy or alpha claim"
    )
    return {
        "diagnostic": FIXED_SIGNAL_DIAGNOSTIC_SPEC["diagnostic"],
        "discovery_only": True,
        "supplemental_only": True,
        "fixed_spec": FIXED_SIGNAL_DIAGNOSTIC_SPEC,
        "instrument_id": instrument_id,
        "family_id": family.family_id,
        "mechanism_label": mechanism,
        "rule": json.loads(rule_source_json(rule)),
        "hashes": {
            "family_hash": family_hash,
            "rule_hash": rule_hash,
            "code_hash": code_hash,
            "dataset_hash": dataset_hash,
            "manifest_identity_hash": dataset_hash,
        },
        "family_hash": family_hash,
        "rule_hash": rule_hash,
        "code_hash": code_hash,
        "dataset_hash": dataset_hash,
        "split": manifest.split,
        "source_start": manifest.source_start,
        "source_end": manifest.source_end,
        "sampled_event_count": len(event_rows),
        "event_timestamps": [event["event_ts"] for event in event_rows],
        "exclusions": {
            "signal": signal_exclusions,
            "horizons": {horizon: dict(sorted(reasons.items())) for horizon, reasons in horizon_exclusions.items()},
        },
        "overall": {horizon: _summary(rows) for horizon, rows in sorted(overall.items())},
        "per_utc_day": {
            day: {horizon: _summary(rows) for horizon, rows in sorted(horizons.items())}
            for day, horizons in sorted(by_day.items())
        },
        "events": event_rows,
        "no_significance_or_alpha_claim": True,
    }


def rule_source_json(rule: RuleSpec) -> str:
    from evolution.rules import canonical_rule_json
    return canonical_rule_json(rule)


def _summary(rows: list[dict[str, object]]) -> dict[str, float | int | None]:
    count = len(rows)
    gross = [float(row["gross_bps"]) for row in rows]
    net = [float(row["net_bps"]) for row in rows]
    return {
        "count": count,
        "gross_bps_mean": sum(gross) / count if count else None,
        "gross_bps_sum": sum(gross) if count else 0.0,
        "net_bps_mean": sum(net) / count if count else None,
        "net_bps_sum": sum(net) if count else 0.0,
        "win_rate": sum(value > 0 for value in net) / count if count else None,
    }


def _validate_manifest_bounds(manifest: DatasetManifest, window) -> None:
    if _parse_manifest_datetime(manifest.source_start) != window.start:
        raise ValueError("dataset manifest UTC start does not match request")
    if _parse_manifest_datetime(manifest.source_end) != window.end:
        raise ValueError("dataset manifest UTC end does not match request")


def _safe_timestamp(value: object) -> int | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        timestamp = int(value)
        return timestamp if timestamp == value and timestamp >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _finite_float(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _utc_day(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp / 1_000_000_000, tz=UTC).date().isoformat()


__all__ = [
    "EVENT_SPACING_MINUTES",
    "FIXED_SIGNAL_DIAGNOSTIC_SPEC",
    "HORIZONS_MINUTES",
    "build_supplemental_signal_diagnostic",
    "collect_entry_events",
    "executable_bps",
    "run_supplemental_signal_diagnostic",
]
