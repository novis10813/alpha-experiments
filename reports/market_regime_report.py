"""Market regime characterization report (discovery-only diagnostic).

Characterizes daily market regimes (volatility x trend x direction) across the
registered discovery folds and the supplemental discovery splits, so the
extended discovery calendar in docs/research/market-regime-characterization.md
can document which market regimes the extended discovery data covers.

Preregistered rules (see docs/research/market-regime-characterization.md):

- Complete day: at least 600 one-minute EvolutionMarketState closes.
- r_d: simple daily return, close(last minute of d) / close(last minute of
  d-1) - 1. Null when the previous UTC day is absent from the sample.
- sigma_d: sample standard deviation of one-minute log returns within day d,
  annualized by sqrt(525600).
- eff_d: |close_d - open_d| / sum(|one-minute close changes|) within day d
  (Kaufman efficiency ratio at daily granularity). Null when the denominator
  is zero.
- Trailing baseline: the up-to-30 complete UTC days strictly before d (all
  available earlier complete days for the first 30 days). Trailing only.
- Vol regime: high_vol when sigma_d >= median(trailing sigma), else low_vol.
- Trend regime (rule C, preregistered 2026-09-21): trending when BOTH
  |r_d| >= 2 * median(trailing |r|) and eff_d >= 2 * median(trailing eff),
  else non_trending.
- Direction: up / down / flat from the sign of r_d.
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
TRAILING_WINDOW_DAYS = 30
TREND_MULTIPLIER = 2.0
ANNUALIZATION_SECONDS_PER_YEAR = 525_600

ALL_INSTRUMENTS = ("BTCUSDT.BINANCE", "ETHUSDT.BINANCE", "BNBUSDT.BINANCE")
ORIGINAL_FOLD_NAMES = tuple(f"discovery_{i}" for i in range(1, 6))

DEFAULT_V2_ROOT = Path(".local/evolution-data-v2")
DEFAULT_LEGACY_ROOT = Path(".local/evolution-data")
DEFAULT_SUPPLEMENTAL_ROOT = Path(".local/evolution-data-supplemental")

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
    daily_return: float | None


@dataclass(frozen=True)
class DayRegime:
    """Classified regime row for one UTC day."""

    day: str
    source_split: str
    manifest_schema: int
    close_count: int
    daily_return: float | None
    sigma_annualized: float | None
    path_efficiency: float | None
    status: str
    vol_regime: str | None
    trend_regime: str | None
    direction: str | None
    regime_label: str | None


def default_split_map(
    v2_root: Path = DEFAULT_V2_ROOT,
    legacy_root: Path = DEFAULT_LEGACY_ROOT,
    supplemental_root: Path = DEFAULT_SUPPLEMENTAL_ROOT,
) -> dict[str, InstrumentSplits]:
    """Split table from docs/superpowers/plans/2026-09-21-supplemental-data-market-regime.md."""
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


def vol_rule_1x_median(sigma: float, sigma_baseline: Sequence[float]) -> str:
    """high_vol when sigma is at or above the trailing baseline median."""
    return "high_vol" if sigma >= statistics.median(sigma_baseline) else "low_vol"


def trend_rule_c_magnitude_and_efficiency_2x_median(
    abs_daily_return: float,
    abs_return_baseline: Sequence[float],
    path_efficiency: float | None,
    efficiency_baseline: Sequence[float],
) -> bool:
    """Preregistered trend rule (candidate C, 2x trailing median, 2026-09-21).

    A day is trending iff it is BOTH large in magnitude and efficient in
    path, each at or above twice the trailing baseline median. Magnitude
    alone would label violent V-shaped reversal days as trending; path
    efficiency alone would label small-range low-volatility drift days.
    """
    if not abs_return_baseline or path_efficiency is None or not efficiency_baseline:
        return False
    magnitude_ok = abs_daily_return >= TREND_MULTIPLIER * statistics.median(abs_return_baseline)
    efficiency_ok = path_efficiency >= TREND_MULTIPLIER * statistics.median(efficiency_baseline)
    return magnitude_ok and efficiency_ok


def _direction(daily_return: float | None) -> str | None:
    if daily_return is None:
        return None
    if daily_return > 0:
        return "up"
    if daily_return < 0:
        return "down"
    return "flat"


def classify_days(observations: Sequence[DayObservation]) -> list[DayRegime]:
    """Classify vol x trend x direction for each day using trailing baselines only."""
    regimes: list[DayRegime] = []
    eligible_prior: list[DayObservation] = []
    for obs in sorted(observations, key=lambda item: item.day):
        if obs.close_count < MIN_CLOSES_PER_DAY:
            regimes.append(
                DayRegime(
                    day=obs.day,
                    source_split=obs.source_split,
                    manifest_schema=obs.manifest_schema,
                    close_count=obs.close_count,
                    daily_return=obs.daily_return,
                    sigma_annualized=obs.sigma_annualized,
                    path_efficiency=obs.path_efficiency,
                    status="insufficient_data",
                    vol_regime=None,
                    trend_regime=None,
                    direction=_direction(obs.daily_return),
                    regime_label=None,
                ),
            )
            continue

        window = eligible_prior[-TRAILING_WINDOW_DAYS:]
        sigma_baseline = [p.sigma_annualized for p in window if p.sigma_annualized is not None]
        abs_return_baseline = [abs(p.daily_return) for p in window if p.daily_return is not None]
        efficiency_baseline = [p.path_efficiency for p in window if p.path_efficiency is not None]

        vol_regime = None
        if obs.sigma_annualized is not None and sigma_baseline:
            vol_regime = vol_rule_1x_median(obs.sigma_annualized, sigma_baseline)
        trend_regime = None
        if obs.daily_return is not None:
            trending = trend_rule_c_magnitude_and_efficiency_2x_median(
                abs(obs.daily_return), abs_return_baseline, obs.path_efficiency, efficiency_baseline
            )
            trend_regime = "trending" if trending else "non_trending"
        direction = _direction(obs.daily_return)
        classified = vol_regime is not None and trend_regime is not None
        regime = DayRegime(
            day=obs.day,
            source_split=obs.source_split,
            manifest_schema=obs.manifest_schema,
            close_count=obs.close_count,
            daily_return=obs.daily_return,
            sigma_annualized=obs.sigma_annualized,
            path_efficiency=obs.path_efficiency,
            status="classified" if classified else "no_baseline",
            vol_regime=vol_regime,
            trend_regime=trend_regime,
            direction=direction,
            regime_label=(f"{vol_regime}_{trend_regime}_{direction}" if classified else None),
        )
        regimes.append(regime)
        eligible_prior.append(obs)
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
        "schema_version": 1,
        "report": "market-regime-map",
        "scope": "discovery-only diagnostic; not a factor, no fitness or promotion use",
        "rules": {
            "complete_day_min_closes": MIN_CLOSES_PER_DAY,
            "trailing_window_days": TRAILING_WINDOW_DAYS,
            "annualization_seconds_per_year": ANNUALIZATION_SECONDS_PER_YEAR,
            "vol_regime": "high_vol iff sigma_d >= median(trailing up-to-30 complete days sigma); else low_vol",
            "trend_regime": (
                "rule C (2026-09-21): trending iff |r_d| >= 2*median(trailing |r|) AND "
                "eff_d >= 2*median(trailing eff); else non_trending"
            ),
            "direction": "up/down/flat from the sign of r_d",
            "regime_label": "<vol_regime>_<trend_regime>_<direction>",
            "day_assignment": "calendar day = (ts_event - 60s) // 86400s; state interval ends at ts_event",
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
