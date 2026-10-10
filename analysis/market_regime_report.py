"""Market regime characterization report (discovery-only diagnostic).

Characterizes daily market regimes (volatility x trend x direction) across the
registered discovery folds and the supplemental discovery splits, so the
extended discovery calendar in tasks/T07-market-regime/REPORT.md
can document which market regimes the extended discovery data covers.

Preregistered rules v2 (see tasks/T07-market-regime/REPORT.md):

- Complete day: at least 600 one-minute EvolutionMarketState closes.
- r3_d: 3-complete-day cumulative return, close_d / close_base - 1, where
  base is the 3rd-most-recent complete day at or before d (the span holds
  exactly 3 complete days; calendar gaps tolerated). Null when the span
  cannot be formed.
- eff3_d: |close_d - close_base| / sum of one-minute path length over the
  same 3 complete days. Null when the denominator is zero.
- sigma_d: sample standard deviation of one-minute log returns within day d,
  annualized by sqrt(525600).
- Trailing baseline: the up-to-90 complete UTC days strictly before d; fewer
  than 30 prior complete days -> no_baseline. Trailing only.
- Vol regime: high_vol when sigma_d >= median(trailing sigma), else low_vol.
- Trend regime (hysteresis): enter trending when |r3_d| >= 2.0 x median
  (trailing |r3|) AND eff3_d >= q75(trailing eff3); exit trending when
  |r3_d| < 1.0 x median(trailing |r3|).
- Direction: up / down / flat from r3_d with a deadband: flat when
  |r3_d| <= 0.5 x stdev(trailing r3).
- Break flag (diagnostic only, never changes labels or baselines): two-sided
  CUSUM on (sigma_d - median_90d) / median_90d with k = 0.05, h = 4.0, reset
  on trigger.
- Regime label: "<vol>_<trend>_<direction>", e.g. high_vol_trending_up.

Calendar day assignment: each one-minute state's interval ends at ts_event
(repository convention: completed aggregation states become knowable at the
interval end), so the calendar day of a state is (ts_event - 60s) // 86400s.

Scope: discovery-only diagnostic. Not a factor, not a hypothesis acceptance,
no fitness or promotion use. Reads only local discovery split files; it never
reads validation, holdout, or the remote catalog.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from evolution.market_state import EvolutionMarketState

DAY_NS = 86_400 * 1_000_000_000
MINUTE_NS = 60 * 1_000_000_000
MIN_CLOSES_PER_DAY = 600
# Rule v2 (preregistered; see tasks/T07-market-regime/REPORT.md).
# Candidate sets (selection deferred to the evaluation phase; the primary
# variant below carries the decision):
#   anchor window (days)        {90, 60}
#   trend entry x median(|r3|)  {1.5, 2.0, 3.0}
#   trend exit  x median(|r3|)  {1.0, 1.5}
#   efficiency quantile         {0.50, 0.75, 0.90}
#   direction deadband x stdev  {0.25, 0.5}
#   CUSUM k (relative sigma dev){0.05, 0.10}
#   CUSUM h                     {4.0, 6.0}
TRAILING_WINDOW_DAYS = 90
BASELINE_FLOOR_DAYS = 30
TREND_ENTRY_MULTIPLIER = 2.0
TREND_EXIT_MULTIPLIER = 1.0
EFFICIENCY_QUANTILE = 0.75  # eff3_q75 = statistics.quantiles(values, n=4)[2]
DIRECTION_DEADBAND_SDS = 0.5
CUSUM_K = 0.05
CUSUM_H = 4.0
ANNUALIZATION_SECONDS_PER_YEAR = 525_600

ALL_INSTRUMENTS = ("BTCUSDT.BINANCE", "ETHUSDT.BINANCE", "BNBUSDT.BINANCE")
ORIGINAL_FOLD_NAMES = tuple(f"discovery_{i}" for i in range(1, 6))

DEFAULT_V2_ROOT = Path("data/evolution-data-v2")
DEFAULT_LEGACY_ROOT = Path("data/evolution-data")
DEFAULT_SUPPLEMENTAL_ROOT = Path("data/evolution-data-supplemental")

DEFAULT_OUTPUT = Path("outputs/evolution-diagnostics/market-regime-map.json")


@dataclass(frozen=True)
class InstrumentSplits:
    """Local split locations for one instrument, per the 2026-09-21 plan."""

    instrument_id: str
    original_folds_root: Path
    original_folds: tuple[str, ...]
    supplemental_root: Path
    supplemental_splits: tuple[str, ...]


@dataclass(frozen=True)
class DayObservation:
    """Per-UTC-day statistics for one instrument from one source split."""

    day: str
    source_split: str
    manifest_schema: int
    close_count: int
    first_close: float | None
    last_close: float | None
    sigma_annualized: float | None
    path_efficiency: float | None
    intraday_path_length: float
    daily_return: float | None


@dataclass(frozen=True)
class DayRegime:
    """Classified regime row for one UTC day (rule v2)."""

    day: str
    source_split: str
    manifest_schema: int
    close_count: int
    daily_return: float | None
    r3: float | None
    sigma_annualized: float | None
    eff3: float | None
    sigma_dev: float | None
    path_efficiency: float | None
    status: str
    vol_regime: str | None
    trend_regime: str | None
    direction: str | None
    regime_label: str | None
    break_flag: bool | None
    anchors: dict[str, float | None] | None


def default_split_map(
    v2_root: Path = DEFAULT_V2_ROOT,
    legacy_root: Path = DEFAULT_LEGACY_ROOT,
    supplemental_root: Path = DEFAULT_SUPPLEMENTAL_ROOT,
) -> dict[str, InstrumentSplits]:
    """Split table from tasks/T07-market-regime/REPORT.md (Inputs)."""
    return {
        "BTCUSDT.BINANCE": InstrumentSplits(
            instrument_id="BTCUSDT.BINANCE",
            original_folds_root=v2_root,
            original_folds=ORIGINAL_FOLD_NAMES,
            supplemental_root=supplemental_root,
            supplemental_splits=(
                "discovery_supplemental_20260829_20260830",
                "discovery_supplemental_20260830_20260905",
                "discovery_supplemental_20260905_20260921",
            ),
        ),
        "ETHUSDT.BINANCE": InstrumentSplits(
            instrument_id="ETHUSDT.BINANCE",
            original_folds_root=v2_root,
            original_folds=ORIGINAL_FOLD_NAMES,
            supplemental_root=supplemental_root,
            supplemental_splits=("discovery_supplemental_20260829_20260921",),
        ),
        "BNBUSDT.BINANCE": InstrumentSplits(
            instrument_id="BNBUSDT.BINANCE",
            original_folds_root=legacy_root,
            original_folds=ORIGINAL_FOLD_NAMES,
            supplemental_root=supplemental_root,
            supplemental_splits=("discovery_supplemental_20260829_20260921",),
        ),
    }


def load_day_observations(root: Path, split: str, instrument_id: str) -> tuple[list[DayObservation], dict[str, object]]:
    """Load minute closes from one split and aggregate them into UTC-day statistics."""
    split_dir = root / split / instrument_id
    manifest_path = split_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    catalog = ParquetDataCatalog(split_dir)
    states = [item.data for item in catalog.query(EvolutionMarketState, identifiers=[instrument_id])]
    states.sort(key=lambda state: state.ts_event)

    closes_by_day: dict[int, list[float]] = {}
    for state in states:
        day_index = (state.ts_event - MINUTE_NS) // DAY_NS
        closes_by_day.setdefault(day_index, []).append(state.close)

    observations: list[DayObservation] = []
    for day_index in sorted(closes_by_day):
        closes = closes_by_day[day_index]
        day = (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_index)).strftime("%Y-%m-%d")
        log_returns = [
            math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i] > 0 and closes[i - 1] > 0
        ]
        sigma: float | None = None
        if len(log_returns) >= 2:
            sigma = statistics.stdev(log_returns) * math.sqrt(ANNUALIZATION_SECONDS_PER_YEAR)
        denominator = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
        efficiency: float | None = None
        if denominator > 0.0:
            efficiency = abs(closes[-1] - closes[0]) / denominator
        observations.append(
            DayObservation(
                day=day,
                source_split=split,
                manifest_schema=int(manifest.get("schema_version", -1)),
                close_count=len(closes),
                first_close=closes[0],
                last_close=closes[-1],
                sigma_annualized=sigma,
                path_efficiency=efficiency,
                intraday_path_length=denominator,
                daily_return=None,
            ),
        )

    observed_rows = sum(obs.close_count for obs in observations)
    manifest_rows = manifest.get("row_count")
    record: dict[str, object] = {
        "split": split,
        "source_start": manifest.get("source_start"),
        "source_end": manifest.get("source_end"),
        "manifest_schema": int(manifest.get("schema_version", -1)),
        "execution_profile": manifest.get("execution_profile"),
        "manifest_row_count": manifest_rows,
        "observed_row_count": observed_rows,
        "manifest_row_count_match": manifest_rows is None or manifest_rows == observed_rows,
        "observed_days": len(observations),
        "days_below_min_closes": sum(1 for obs in observations if obs.close_count < MIN_CLOSES_PER_DAY),
    }
    return observations, record


def merge_days(observations_by_split: dict[str, list[DayObservation]]) -> list[DayObservation]:
    """Merge per-split day observations into one chronological series and fill r_d."""
    merged: dict[str, DayObservation] = {}
    for split in sorted(observations_by_split):
        for obs in observations_by_split[split]:
            if obs.day in merged:
                existing = merged[obs.day]
                raise RuntimeError(f"duplicate day {obs.day} in splits {existing.source_split} and {split}")
            merged[obs.day] = obs

    result: list[DayObservation] = []
    previous: DayObservation | None = None
    for day in sorted(merged):
        obs = merged[day]
        daily_return = None
        if (
            previous is not None
            and previous.last_close is not None
            and previous.last_close > 0
            and obs.last_close is not None
            and _days_between(previous.day, obs.day) == 1
        ):
            daily_return = obs.last_close / previous.last_close - 1.0
        result.append(_replace(obs, daily_return=daily_return))
        previous = obs
    return result


def _days_between(day_a: str, day_b: str) -> int:
    date_a = datetime.strptime(day_a, "%Y-%m-%d")
    date_b = datetime.strptime(day_b, "%Y-%m-%d")
    return (date_b - date_a).days


def _replace(obs: DayObservation, **changes: object) -> DayObservation:
    values = asdict(obs)
    values.update(changes)
    return DayObservation(**values)


def _span_features(complete_prior: Sequence[DayObservation], obs: DayObservation) -> tuple[float | None, float | None]:
    """3-complete-day span features for day obs: (r3, eff3).

    base is the 3rd-most-recent complete day at or before obs (the 2nd
    complete day strictly before it); the span is base, the complete day in
    between, and obs. Returns (None, None) when the span cannot be formed,
    and eff3 is None when the span path length is zero.
    """
    if len(complete_prior) < 2:
        return None, None
    base = complete_prior[-2]
    if base.last_close is None or base.last_close <= 0 or obs.last_close is None or obs.last_close <= 0:
        return None, None
    r3 = obs.last_close / base.last_close - 1.0
    span = (base, complete_prior[-1], obs)
    denominator = sum(day.intraday_path_length for day in span)
    if denominator <= 0.0:
        return r3, None
    eff3 = abs(obs.last_close - base.last_close) / denominator
    return r3, eff3


def _unlabeled(obs: DayObservation, *, status: str, r3: float | None = None, eff3: float | None = None) -> DayRegime:
    """Regime row for a day that is not classified (no sub-labels, anchors, or flag)."""
    return DayRegime(
        day=obs.day,
        source_split=obs.source_split,
        manifest_schema=obs.manifest_schema,
        close_count=obs.close_count,
        daily_return=obs.daily_return,
        r3=r3,
        sigma_annualized=obs.sigma_annualized,
        eff3=eff3,
        sigma_dev=None,
        path_efficiency=obs.path_efficiency,
        status=status,
        vol_regime=None,
        trend_regime=None,
        direction=None,
        regime_label=None,
        break_flag=None,
        anchors=None,
    )


def classify_days(observations: Sequence[DayObservation]) -> list[DayRegime]:
    """Classify vol x trend x direction for each day (rule v2).

    Every statistic for day d uses complete days strictly before d; the
    trend state and the CUSUM state carry forward in time only. A future day
    never changes any earlier label.
    """
    regimes: list[DayRegime] = []
    complete_prior: list[DayObservation] = []
    complete_r3: list[float | None] = []
    complete_eff3: list[float | None] = []
    trending = False
    s_plus = 0.0
    s_minus = 0.0
    for obs in sorted(observations, key=lambda item: item.day):
        if obs.close_count < MIN_CLOSES_PER_DAY:
            regimes.append(_unlabeled(obs, status="insufficient_data"))
            continue

        if len(complete_prior) < BASELINE_FLOOR_DAYS:
            r3, eff3 = _span_features(complete_prior, obs)
            regimes.append(_unlabeled(obs, status="no_baseline", r3=r3, eff3=eff3))
            complete_prior.append(obs)
            complete_r3.append(r3)
            complete_eff3.append(eff3)
            continue

        window = complete_prior[-TRAILING_WINDOW_DAYS:]
        sigmas = [p.sigma_annualized for p in window if p.sigma_annualized is not None]
        window_r3 = [value for value in complete_r3[-TRAILING_WINDOW_DAYS:] if value is not None]
        window_eff3 = [value for value in complete_eff3[-TRAILING_WINDOW_DAYS:] if value is not None]

        sigma_median_90 = statistics.median(sigmas) if sigmas else None
        sigma_median_30 = statistics.median(sigmas[-30:]) if sigmas else None
        abs_r3_median = statistics.median(abs(value) for value in window_r3) if window_r3 else None
        eff3_q75 = statistics.quantiles(window_eff3, n=4)[2] if len(window_eff3) >= 2 else None
        r3_sd = statistics.stdev(window_r3) if len(window_r3) >= 2 else None

        r3, eff3 = _span_features(complete_prior, obs)

        vol_regime = "low_vol"
        if obs.sigma_annualized is not None and sigma_median_90 is not None:
            vol_regime = "high_vol" if obs.sigma_annualized >= sigma_median_90 else "low_vol"

        if not trending and r3 is not None and eff3 is not None and abs_r3_median is not None and eff3_q75 is not None:
            if abs(r3) >= TREND_ENTRY_MULTIPLIER * abs_r3_median and eff3 >= eff3_q75:
                trending = True
        elif trending and r3 is not None and abs_r3_median is not None:
            if abs(r3) < TREND_EXIT_MULTIPLIER * abs_r3_median:
                trending = False
        trend_regime = "trending" if trending else "non_trending"

        if r3 is None:
            direction: str | None = None
        elif r3 == 0.0:
            direction = "flat"
        elif r3_sd is None:
            direction = "up" if r3 > 0.0 else "down"
        elif abs(r3) <= DIRECTION_DEADBAND_SDS * r3_sd:
            direction = "flat"
        else:
            direction = "up" if r3 > 0.0 else "down"

        sigma_dev: float | None = None
        break_flag = False
        if obs.sigma_annualized is not None and sigma_median_90 is not None and sigma_median_90 > 0:
            sigma_dev = (obs.sigma_annualized - sigma_median_90) / sigma_median_90
            s_plus = max(0.0, s_plus + sigma_dev - CUSUM_K)
            s_minus = min(0.0, s_minus - sigma_dev - CUSUM_K)
            if max(s_plus, -s_minus) > CUSUM_H:
                break_flag = True
                s_plus = 0.0
                s_minus = 0.0

        regimes.append(
            DayRegime(
                day=obs.day,
                source_split=obs.source_split,
                manifest_schema=obs.manifest_schema,
                close_count=obs.close_count,
                daily_return=obs.daily_return,
                r3=r3,
                sigma_annualized=obs.sigma_annualized,
                eff3=eff3,
                sigma_dev=sigma_dev,
                path_efficiency=obs.path_efficiency,
                status="classified",
                vol_regime=vol_regime,
                trend_regime=trend_regime,
                direction=direction,
                regime_label=f"{vol_regime}_{trend_regime}_{direction}",
                break_flag=break_flag,
                anchors={
                    "sigma_median_90d": sigma_median_90,
                    "sigma_median_30d": sigma_median_30,
                    "abs_r3_median": abs_r3_median,
                    "eff3_q75": eff3_q75,
                    "r3_sd": r3_sd,
                },
            ),
        )
        complete_prior.append(obs)
        complete_r3.append(r3)
        complete_eff3.append(eff3)
    return regimes


def coverage_summary(regimes: Sequence[DayRegime]) -> dict[str, object]:
    classified = [r for r in regimes if r.regime_label is not None]
    by_label: dict[str, int] = {}
    by_quadrant: dict[str, int] = {}
    for regime in classified:
        by_label[regime.regime_label] = by_label.get(regime.regime_label, 0) + 1
        quadrant = f"{regime.vol_regime}_{regime.trend_regime}"
        by_quadrant[quadrant] = by_quadrant.get(quadrant, 0) + 1
    return {
        "days_total": len(regimes),
        "days_classified": len(classified),
        "days_break_flag": sum(1 for regime in classified if regime.break_flag is True),
        "by_label": dict(sorted(by_label.items())),
        "by_quadrant": dict(sorted(by_quadrant.items())),
    }


def supplement_adds(original: dict[str, object], supplemental: dict[str, object]) -> dict[str, list[str]]:
    """Labels materially under-represented in the original folds but present in the supplement."""
    original_days = int(original["days_classified"])
    supplemental_days = int(supplemental["days_classified"])
    original_labels: dict[str, int] = original["by_label"]
    supplemental_labels: dict[str, int] = supplemental["by_label"]
    newly_covered = sorted(
        label for label, count in supplemental_labels.items() if original_labels.get(label, 0) == 0
    )
    underrepresented: list[str] = []
    if original_days and supplemental_days:
        for label, count in supplemental_labels.items():
            original_count = original_labels.get(label, 0)
            if original_count > 0 and original_count / original_days < count / supplemental_days:
                underrepresented.append(label)
    return {
        "newly_covered_labels": newly_covered,
        "underrepresented_in_original_labels": sorted(underrepresented),
    }


def build_instrument_map(split_map: InstrumentSplits) -> dict[str, object]:
    instrument_id = split_map.instrument_id
    observations_by_split: dict[str, list[DayObservation]] = {}
    split_records: list[dict[str, object]] = []
    for split in split_map.original_folds:
        observations, record = load_day_observations(split_map.original_folds_root, split, instrument_id)
        observations_by_split[split] = observations
        split_records.append(record)
    for split in split_map.supplemental_splits:
        observations, record = load_day_observations(split_map.supplemental_root, split, instrument_id)
        observations_by_split[split] = observations
        split_records.append(record)

    regimes = classify_days(merge_days(observations_by_split))
    original_rows = [r for r in regimes if r.source_split in split_map.original_folds]
    supplemental_rows = [r for r in regimes if r.source_split in split_map.supplemental_splits]
    original_summary = coverage_summary(original_rows)
    supplemental_summary = coverage_summary(supplemental_rows)
    return {
        "instrument_id": instrument_id,
        "daily": [asdict(regime) for regime in regimes],
        "coverage": {
            "original_folds": original_summary,
            "supplemental": supplemental_summary,
            "combined": coverage_summary(regimes),
            "supplement_adds": supplement_adds(original_summary, supplemental_summary),
        },
        "splits": split_records,
    }


def build_map(instrument_ids: Sequence[str], split_map: dict[str, InstrumentSplits]) -> dict[str, object]:
    return {
        "schema_version": 2,
        "report": "market-regime-map",
        "scope": "discovery-only diagnostic; not a factor, no fitness or promotion use",
        "rules": {
            "complete_day_min_closes": MIN_CLOSES_PER_DAY,
            "trailing_window_days": TRAILING_WINDOW_DAYS,
            "baseline_floor_days": BASELINE_FLOOR_DAYS,
            "annualization_seconds_per_year": ANNUALIZATION_SECONDS_PER_YEAR,
            "span": "r3/eff3 span the 3rd-most-recent complete day at or before d through d (exactly 3 complete days)",
            "vol_regime": "high_vol iff sigma_d >= median(trailing up-to-90 complete days sigma); else low_vol",
            "trend_regime": (
                "hysteresis: enter trending iff |r3| >= 2.0*median(trailing |r3|) AND eff3 >= q75(trailing eff3); "
                "exit trending iff |r3| < 1.0*median(trailing |r3|)"
            ),
            "direction": "flat iff |r3| <= 0.5*stdev(trailing r3); else up/down by sign of r3",
            "break_flag": (
                "two-sided CUSUM on (sigma_d - median_90d)/median_90d, k=0.05 h=4.0, reset on trigger; "
                "diagnostic only, never changes labels or baselines"
            ),
            "regime_label": "<vol_regime>_<trend_regime>_<direction>",
            "day_assignment": "calendar day = (ts_event - 60s) // 86400s; state interval ends at ts_event",
            "candidate_sets": {
                "anchor_window_days": [90, 60],
                "trend_entry_x_median_abs_r3": [1.5, 2.0, 3.0],
                "trend_exit_x_median_abs_r3": [1.0, 1.5],
                "efficiency_quantile": [0.50, 0.75, 0.90],
                "direction_deadband_x_stdev_r3": [0.25, 0.5],
                "cusum_k": [0.05, 0.10],
                "cusum_h": [4.0, 6.0],
            },
            "selection_rule": (
                "training-window-only selection; the primary variant carries the decision; "
                "preregistration: tasks/T07-market-regime/REPORT.md (v2 section)"
            ),
        },
        "instruments": {instrument_id: build_instrument_map(split_map[instrument_id]) for instrument_id in instrument_ids},
    }


def write_map(payload: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write the discovery-only market regime map JSON.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--instruments", nargs="+", default=list(ALL_INSTRUMENTS), choices=list(ALL_INSTRUMENTS))
    parser.add_argument("--v2-root", type=Path, default=DEFAULT_V2_ROOT)
    parser.add_argument("--legacy-root", type=Path, default=DEFAULT_LEGACY_ROOT)
    parser.add_argument("--supplemental-root", type=Path, default=DEFAULT_SUPPLEMENTAL_ROOT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    split_map = default_split_map(
        v2_root=args.v2_root, legacy_root=args.legacy_root, supplemental_root=args.supplemental_root
    )
    payload = build_map(args.instruments, split_map)
    write_map(payload, args.output)
    print(f"wrote market regime map to {args.output}")
    for instrument_id in args.instruments:
        instrument = payload["instruments"][instrument_id]
        coverage = instrument["coverage"]
        combined = coverage["combined"]
        print(
            f"{instrument_id}: days={combined['days_total']} "
            f"classified={combined['days_classified']} "
            f"quadrants={json.dumps(combined['by_quadrant'], sort_keys=True)}"
        )
        print(
            f"  supplement_adds newly_covered="
            f"{coverage['supplement_adds']['newly_covered_labels']} "
            f"underrepresented={coverage['supplement_adds']['underrepresented_in_original_labels']}"
        )


if __name__ == "__main__":
    main()
