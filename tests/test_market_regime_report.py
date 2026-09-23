"""Tests for reports.market_regime_report (synthetic fixtures, no parquet)."""

from __future__ import annotations

import unittest

from reports.market_regime_report import DayObservation, classify_days, merge_days


def _obs(day: int, source_split: str = "split_a", *, r: float | None = 0.01, sigma: float = 1.0, eff: float = 0.25,
         close_count: int = 1440, schema: int = 2) -> DayObservation:
    return DayObservation(
        day=f"2026-06-{day:02d}",
        source_split=source_split,
        manifest_schema=schema,
        close_count=close_count,
        first_close=100.0,
        last_close=101.0,
        sigma_annualized=sigma,
        path_efficiency=eff,
        daily_return=r,
    )


def _hand_computable_fixture() -> list[DayObservation]:
    """34 days: 30 flat baseline days (r=0.01, sigma=1.0, eff=0.25) plus four probe days."""
    observations = [_obs(1, r=None)]
    for day in range(2, 31):
        observations.append(_obs(day))
    # d30: large magnitude AND high efficiency -> trending; low vol.
    observations.append(_obs(30, r=0.05, sigma=0.5, eff=0.6))
    # d31: small magnitude, high efficiency -> not trending (efficiency alone must not trigger); high vol.
    observations.append(_obs(31, r=-0.005, sigma=2.0, eff=0.9))
    # d32: large magnitude, low efficiency -> not trending (magnitude alone must not trigger); high vol.
    observations.append(_obs(32, r=0.06, sigma=1.0, eff=0.3))
    # d33: small magnitude, high efficiency -> not trending; high vol.
    observations.append(_obs(33, r=0.005, sigma=1.0, eff=0.99))
    # d34: spare day used by the trailing-only test.
    observations.append(_obs(34, r=0.01, sigma=1.0, eff=0.25))
    return observations


class ClassificationHandComputableTest(unittest.TestCase):
    def test_vol_trend_direction_labels(self):
        regimes = {r.day: r for r in classify_days(_hand_computable_fixture())}

        first = regimes["2026-06-01"]
        self.assertIsNone(first.daily_return)
        self.assertEqual(first.status, "no_baseline")
        self.assertIsNone(first.regime_label)

        # Baseline day: sigma at the trailing median -> high_vol; |r| below 2x median -> non_trending.
        self.assertEqual(regimes["2026-06-29"].regime_label, "high_vol_non_trending_up")

        # d30: |r|=0.05 >= 2*0.01 and eff=0.6 >= 2*0.25 -> trending; sigma 0.5 < 1.0 -> low_vol.
        self.assertEqual(regimes["2026-06-30"].regime_label, "low_vol_trending_up")

        # d31: magnitude fails (0.005 < 0.02), efficiency passes -> non_trending; down; high vol.
        self.assertEqual(regimes["2026-06-31"].regime_label, "high_vol_non_trending_down")

        # d32: magnitude passes (0.06 >= 0.02), efficiency fails (0.3 < 0.5) -> non_trending; up.
        self.assertEqual(regimes["2026-06-32"].regime_label, "high_vol_non_trending_up")

        # d33: efficiency passes, magnitude fails -> non_trending; up.
        self.assertEqual(regimes["2026-06-33"].regime_label, "high_vol_non_trending_up")


class TrailingOnlyBaselineTest(unittest.TestCase):
    def test_future_day_does_not_change_earlier_labels(self):
        fixture = _hand_computable_fixture()
        original = classify_days(fixture)

        shifted = list(fixture[:-1]) + [
            _obs(34, r=0.9, sigma=999.0, eff=1.0),
        ]
        modified = classify_days(shifted)

        self.assertEqual(original[:-1], modified[:-1])


class InsufficientDayExclusionTest(unittest.TestCase):
    def _fixture(self) -> list[DayObservation]:
        return [
            _obs(1, r=None, eff=0.5),
            _obs(2, r=0.005, eff=0.5),
            # Insufficient day (500 < 600 closes) with extreme values that must not enter baselines.
            _obs(3, r=0.01, sigma=99.0, eff=1.0, close_count=500),
            _obs(4, r=0.012, sigma=1.0, eff=1.0),
        ]

    def test_insufficient_day_status_and_exclusion_from_baseline(self):
        regimes = {r.day: r for r in classify_days(self._fixture())}

        insufficient = regimes["2026-06-03"]
        self.assertEqual(insufficient.status, "insufficient_data")
        self.assertIsNone(insufficient.regime_label)
        self.assertIsNone(insufficient.vol_regime)
        self.assertIsNone(insufficient.trend_regime)
        self.assertEqual(insufficient.direction, "up")

        # d4 baseline = complete days {d1, d2} only. |r| threshold = 2*0.005 = 0.01 -> 0.012 passes.
        # eff threshold = 2*0.5 = 1.0 -> 1.0 passes. If the insufficient day leaked into the
        # |r| baseline the threshold would be 2*median(0.005, 0.01) = 0.015 and d4 would fail.
        self.assertEqual(regimes["2026-06-04"].regime_label, "high_vol_trending_up")


class SourceSplitAttributionTest(unittest.TestCase):
    def test_attribution_preserved(self):
        observations = [
            _obs(1, source_split="split_a", r=None, eff=0.5),
            _obs(2, source_split="split_b", r=0.005, eff=0.5),
            _obs(3, source_split="split_a", r=0.012, eff=1.0),
        ]
        regimes = classify_days(merge_days({"split_a": [observations[0], observations[2]], "split_b": [observations[1]]}))
        self.assertEqual([r.source_split for r in regimes], ["split_a", "split_b", "split_a"])
        self.assertEqual([r.manifest_schema for r in regimes], [2, 2, 2])

    def test_duplicate_day_across_splits_rejected(self):
        with self.assertRaises(RuntimeError):
            merge_days({"split_a": [_obs(1)], "split_b": [_obs(1, source_split="split_b")]})


if __name__ == "__main__":
    unittest.main()
