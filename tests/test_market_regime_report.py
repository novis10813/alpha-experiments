"""Tests for analysis.market_regime_report rule v2 (synthetic fixtures, no parquet).

All expected values are hand-verifiable from the rule in
tasks/T07-market-regime/REPORT.md (v2 section):

  r3_d  = close_d / close_base - 1
          (base = 3rd-most-recent complete day at or before d, i.e. the 2nd
          complete day strictly before d; the span holds exactly 3 complete days)
  eff3  = |close_d - close_base| / (intraday path length over those 3 days)
  vol   = high_vol iff sigma_d >= median(trailing up-to-90 complete days sigma)
  trend = hysteresis: enter iff |r3| >= 2.0*median(trailing |r3|) AND
          eff3 >= q75(trailing eff3); exit iff |r3| < 1.0*median(trailing |r3|)
  dir   = flat iff |r3| <= 0.5*stdev(trailing r3); else up/down by sign of r3
  floor = no_baseline with fewer than 30 prior complete days

DRIFT = 1.5 is used for baseline paths because 1.5 is exactly representable
in binary floating point: closes = 100 * 1.5**(i-1) are exact (below 2**53)
for the early days, so baseline r3 values are 1.25 up to the last ulp and the
trailing stdev over an all-baseline window is exactly 0.0. Probe ratios are
kept off the rule thresholds so float round-trip error cannot flip a decision.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict

import unittest

from analysis.market_regime_report import DayObservation, classify_days, merge_days

DRIFT = 1.5
BASE_R3 = DRIFT**2 - 1.0  # exactly 1.25


def _day_str(index: int) -> str:
    # String-ordered days. classify_days never parses them (only merge_days
    # does, and the merge_days tests below use real calendar dates), so day
    # numbers beyond a month's length are safe.
    return f"2026-06-{index:02d}"


def _obs(
    day: str,
    source_split: str = "split_a",
    *,
    close: float,
    r: float | None = None,
    sigma: float = 1.0,
    path: float = 1.0,
    close_count: int = 1440,
    schema: int = 2,
) -> DayObservation:
    return DayObservation(
        day=day,
        source_split=source_split,
        manifest_schema=schema,
        close_count=close_count,
        first_close=close,
        last_close=close,
        sigma_annualized=sigma,
        path_efficiency=None,
        intraday_path_length=path,
        daily_return=r,
    )


def _baseline_days(n: int = 30, *, path: float = 1.0, sigma: float = 1.0, schema: int = 2) -> list[DayObservation]:
    """n drift complete days: close_i = 100 * DRIFT**(i-1) (exact in binary)."""
    days: list[DayObservation] = []
    close = 100.0
    for i in range(1, n + 1):
        days.append(_obs(_day_str(i), close=close, sigma=sigma, path=path, schema=schema))
        close *= DRIFT
    return days


class HandComputableLabelsTest(unittest.TestCase):
    """T1: vol boundary, trend entry, hysteresis stay/exit, deadband direction."""

    @staticmethod
    def _fixture() -> tuple[list[DayObservation], list[float]]:
        closes = [100.0 * DRIFT ** (i - 1) for i in range(1, 36)]
        # Probe overrides (order matters: each ratio is set against its real base):
        closes[32] = closes[30] * 4.5  # day 33: r3 = 3.5 (>= 2*1.25) -> trend entry
        closes[33] = closes[31] * 2.5  # day 34: r3 = 1.5 (in [1.25, 2.5)) -> hysteresis stay
        closes[34] = closes[32] * 1.5  # day 35: r3 = 0.5 (< 1.25) -> hysteresis exit
        days = [
            _obs(_day_str(i + 1), close=closes[i], sigma={32: 2.0, 33: 0.5}.get(i + 1, 1.0))
            for i in range(35)
        ]
        return days, closes

    def test_vol_trend_direction_labels(self):
        days, closes = HandComputableLabelsTest._fixture()
        regimes = {r.day: r for r in classify_days(days)}

        # Floor: days 1-30 have fewer than 30 prior complete days.
        for i in range(1, 31):
            self.assertEqual(regimes[_day_str(i)].status, "no_baseline")
            self.assertIsNone(regimes[_day_str(i)].regime_label)

        # Day 31: first classified. sigma 1.0 == median -> high_vol (boundary);
        # r3 1.25 < 2*1.25 -> non_trending; r3_sd 0.0 and r3 != 0 -> up.
        self.assertEqual(regimes[_day_str(31)].status, "classified")
        self.assertEqual(regimes[_day_str(31)].regime_label, "high_vol_non_trending_up")

        # Day 32: sigma 2.0 -> high_vol; r3 1.25 -> non_trending; up.
        self.assertEqual(regimes[_day_str(32)].regime_label, "high_vol_non_trending_up")

        # Day 33: r3 3.5 >= 2.5 AND eff3 >= q75 -> trending; sigma 0.5 < 1.0 -> low_vol; up.
        self.assertEqual(regimes[_day_str(33)].regime_label, "low_vol_trending_up")

        # Day 34: r3 1.5 < entry threshold but >= exit threshold -> stays trending; high_vol; up.
        self.assertEqual(regimes[_day_str(34)].regime_label, "high_vol_trending_up")

        # Day 35: r3 0.5 < 1.25 -> exits trending; high_vol; up.
        self.assertEqual(regimes[_day_str(35)].regime_label, "high_vol_non_trending_up")

    def test_day_31_anchors_exact(self):
        days, closes = HandComputableLabelsTest._fixture()
        regime = next(r for r in classify_days(days) if r.day == _day_str(31))

        self.assertEqual(regime.anchors["sigma_median_90d"], 1.0)
        self.assertEqual(regime.anchors["sigma_median_30d"], 1.0)
        # Baseline r3 values are all exactly 1.25.
        self.assertEqual(regime.anchors["abs_r3_median"], BASE_R3)
        self.assertEqual(regime.anchors["r3_sd"], 0.0)
        # eff3_i = (close_i - close_{i-2}) / 3 for i in 3..30 (window at day 31).
        expected_eff3 = [(closes[i - 1] - closes[i - 3]) / 3.0 for i in range(3, 31)]
        self.assertEqual(regime.anchors["eff3_q75"], statistics.quantiles(expected_eff3, n=4)[2])

    def test_break_flag_quiet_on_quiet_baseline(self):
        days, _ = HandComputableLabelsTest._fixture()
        regimes = classify_days(days)
        # sigma_dev: day 32 = (2.0-1.0)/1.0 = 1.0 (S+ = 0.95 < 4); day 33 = -0.5.
        self.assertEqual(regimes[31].sigma_dev, 1.0)
        self.assertEqual(regimes[32].sigma_dev, -0.5)
        classified = [r for r in regimes if r.status == "classified"]
        self.assertTrue(all(r.break_flag is False for r in classified))


class BaselineFloorTest(unittest.TestCase):
    """T2: exactly 29 prior complete days -> no_baseline; 30 -> classified."""

    def test_floor_boundary(self):
        regimes = {r.day: r for r in classify_days(_baseline_days(31))}
        self.assertEqual(regimes[_day_str(30)].status, "no_baseline")
        self.assertIsNone(regimes[_day_str(30)].regime_label)
        self.assertEqual(regimes[_day_str(31)].status, "classified")
        self.assertIsNotNone(regimes[_day_str(31)].regime_label)


class EfficiencyReachableTest(unittest.TestCase):
    """T3 (documented v1 defect): when the trailing efficiency median exceeds
    0.5, the v1 2x-median efficiency threshold was unreachable (eff bounded by
    1.0 within a day). v2's q75-of-own-distribution threshold stays reachable:
    a probe day that is both large and efficient MUST be labeled trending."""

    @staticmethod
    def _close(i: int) -> float:
        # Period-2 step: close_i - close_{i-2} = 1.8 exactly for i >= 3.
        return 100.0 + 1.8 * ((i - 1) // 2) + (1.0 if i % 2 == 0 else 0.0)

    def test_trending_when_efficiency_median_above_half(self):
        days = [_obs(_day_str(i), close=self._close(i)) for i in range(1, 31)]
        probe_close = self._close(29) + 5.0  # day 31: r3 = 5/125.2, eff3 = 5/3
        days.append(_obs(_day_str(31), close=probe_close))

        # Fixture self-check: baseline eff3 is exactly 0.6 for every span day,
        # so the trailing efficiency median is 0.6 > 0.5 (the v1 bug condition).
        baseline_eff3 = [1.8 / 3.0 for _ in range(28)]
        self.assertGreater(statistics.median(baseline_eff3), 0.5)
        # And the probe clears both entry conditions.
        baseline_r3 = [1.8 / self._close(i - 2) for i in range(3, 31)]
        r3_probe = 5.0 / self._close(29)
        self.assertGreaterEqual(r3_probe, 2.0 * statistics.median(baseline_r3))
        self.assertGreaterEqual(5.0 / 3.0, statistics.quantiles(baseline_eff3, n=4)[2])

        regime = next(r for r in classify_days(days) if r.day == _day_str(31))
        # vol: sigma 1.0 == median 1.0 -> high_vol; direction: |r3| well above
        # 0.5 * stdev(trailing r3) -> up.
        self.assertEqual(regime.regime_label, "high_vol_trending_up")


class HysteresisTest(unittest.TestCase):
    """T4: enter at 2x median |r3|; stay in the (1x, 2x) band; exit below 1x;
    re-entry afterwards requires the full entry condition again."""

    def test_enter_stay_exit_reentry(self):
        closes = [100.0 * DRIFT ** (i - 1) for i in range(1, 36)]
        closes[31] = closes[29] * 4.0  # day 32: r3 = 3.0 (above entry threshold)
        closes[32] = closes[30] * 2.5  # day 33: r3 = 1.5 (hysteresis band)
        closes[33] = closes[31] * 1.5  # day 34: r3 = 0.5 (exit)
        closes[34] = closes[32] * 2.5  # day 35: r3 = 1.5 (band, no re-entry)
        days = [_obs(_day_str(i + 1), close=closes[i]) for i in range(35)]

        # Fixture self-check: the trailing median |r3| stays ~1.25 for every
        # probe day (3 outliers among 30 window values cannot move it), so
        # entry needs |r3| >= ~2.5 and exit needs |r3| < ~1.25. All probe r3
        # values are kept off the thresholds (float round-trip margin).
        self.assertGreater(3.0, 2.0 * BASE_R3)
        self.assertGreater(1.5, 1.0 * BASE_R3)
        self.assertLess(1.5, 2.0 * BASE_R3)
        self.assertLess(0.5, 1.0 * BASE_R3)

        regimes = classify_days(days)
        by_day = {r.day: r for r in regimes}
        trends = [by_day[_day_str(i)].trend_regime for i in range(31, 36)]
        self.assertEqual(
            trends,
            ["non_trending", "trending", "trending", "non_trending", "non_trending"],
        )


class CusumBreakFlagTest(unittest.TestCase):
    """T5: quiet baseline -> no flags; a sigma shock day -> flag exactly once;
    the following normal day proves the reset."""

    def test_shock_day_flag_and_reset(self):
        closes = [100.0 * DRIFT ** (i - 1) for i in range(1, 35)]
        days = [_obs(_day_str(i + 1), close=closes[i], sigma={33: 10.0}.get(i + 1, 1.0)) for i in range(34)]
        regimes = classify_days(days)
        classified = [r for r in regimes if r.status == "classified"]
        self.assertEqual([r.day for r in classified], [_day_str(i) for i in (31, 32, 33, 34)])

        # Day 33: median_90d = 1.0 -> sigma_dev = (10-1)/1 = 9 -> S+ = 8.95 > 4.
        self.assertEqual(classified[2].sigma_dev, 9.0)
        self.assertEqual([r.break_flag for r in classified], [False, False, True, False])
        self.assertEqual([r.sigma_dev for r in classified], [0.0, 0.0, 9.0, 0.0])


class TrailingOnlyBaselineTest(unittest.TestCase):
    """T6: an extreme future day must not change any earlier label."""

    def test_future_day_does_not_change_earlier_labels(self):
        fixture, closes = HandComputableLabelsTest._fixture()
        original = classify_days(fixture)

        shifted = list(fixture[:-1]) + [
            _obs(_day_str(35), close=closes[32] * 1.09, sigma=999.0, path=0.1),
        ]
        modified = classify_days(shifted)

        self.assertEqual(original[:-1], modified[:-1])


class InsufficientDayExclusionTest(unittest.TestCase):
    """T7: an insufficient day with extreme values must not enter any baseline
    (asserted through r3_sd, which a leak would distort)."""

    def test_insufficient_day_status_and_exclusion_from_baseline(self):
        days = _baseline_days(31)
        # Day 32: insufficient (500 < 600 closes) with extreme values.
        days.append(_obs(_day_str(32), close=10000.0, sigma=99.0, close_count=500))
        # Day 33: probe on the baseline continuation.
        days.append(_obs(_day_str(33), close=100.0 * DRIFT**32))
        regimes = {r.day: r for r in classify_days(days)}

        insufficient = regimes[_day_str(32)]
        self.assertEqual(insufficient.status, "insufficient_data")
        self.assertIsNone(insufficient.regime_label)
        self.assertIsNone(insufficient.vol_regime)
        self.assertIsNone(insufficient.trend_regime)
        self.assertIsNone(insufficient.direction)
        self.assertIsNone(insufficient.anchors)
        self.assertIsNone(insufficient.break_flag)

        probe = regimes[_day_str(33)]
        self.assertEqual(probe.status, "classified")
        # Window = the 31 complete days (days 1-31); their r3 are all exactly
        # 1.25. If the insufficient day leaked in, its r3 (~7.5) would make
        # stdev O(1) instead of 0.0.
        self.assertEqual(probe.anchors["r3_sd"], 0.0)
        self.assertEqual(probe.anchors["abs_r3_median"], BASE_R3)
        self.assertEqual(probe.regime_label, "high_vol_non_trending_up")


class SchemaInvarianceTest(unittest.TestCase):
    """T8 (BNB schema-1 guard): classification reads only close-derived
    quantities; the manifest schema field must be inert."""

    def test_schema_field_does_not_change_labels(self):
        fixture_a = _baseline_days(34, schema=2)
        fixture_b = _baseline_days(34, schema=1)
        results_a = classify_days(fixture_a)
        results_b = classify_days(fixture_b)

        self.assertEqual([r.manifest_schema for r in results_a], [2] * 34)
        self.assertEqual([r.manifest_schema for r in results_b], [1] * 34)
        for a, b in zip(results_a, results_b):
            self.assertEqual(
                {k: v for k, v in asdict(a).items() if k != "manifest_schema"},
                {k: v for k, v in asdict(b).items() if k != "manifest_schema"},
            )


class SourceSplitAttributionTest(unittest.TestCase):
    """T9: split attribution and duplicate-day rejection (real dates here,
    since merge_days parses them)."""

    def test_attribution_preserved(self):
        observations = [
            _obs("2026-06-01", source_split="split_a", close=100.0),
            _obs("2026-06-02", source_split="split_b", close=101.0),
            _obs("2026-06-03", source_split="split_a", close=102.0),
        ]
        regimes = classify_days(
            merge_days({"split_a": [observations[0], observations[2]], "split_b": [observations[1]]})
        )
        self.assertEqual([r.source_split for r in regimes], ["split_a", "split_b", "split_a"])
        self.assertEqual([r.manifest_schema for r in regimes], [2, 2, 2])
        # Three days cannot reach the 30-day baseline floor.
        self.assertEqual([r.status for r in regimes], ["no_baseline"] * 3)

    def test_duplicate_day_across_splits_rejected(self):
        with self.assertRaises(RuntimeError):
            merge_days(
                {
                    "split_a": [_obs("2026-06-01", close=100.0)],
                    "split_b": [_obs("2026-06-01", source_split="split_b", close=100.0)],
                }
            )


if __name__ == "__main__":
    unittest.main()
