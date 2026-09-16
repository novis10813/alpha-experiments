import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from data.orderbook_quotes import QuoteRow


@dataclass(frozen=True)
class FakeManifest:
    schema_version: int
    instrument_id: str
    split: str
    source_start: str
    source_end: str
    row_count: int
    missing_bucket_count: int
    first_ts_event: int | None
    last_ts_event: int | None
    files: dict[str, str]
    execution_profile: str = "fast"
    quote_interval_seconds: int = 60
    execution_delay_seconds: int = 0
    quote_count: int = 0


class EvolutionCoverageTests(unittest.TestCase):
    def test_report_is_discovery_only_and_reports_labels_and_manifest_profile(self):
        from evolution.coverage import build_discovery_coverage_report
        from evolution.spec import DISCOVERY_FOLDS

        instrument_id = "BTCUSDT.BINANCE"
        split_data = {
            window.name: self._fold_states(window.start.timestamp() * 1_000_000_000, 61)
            for window in DISCOVERY_FOLDS
        }
        manifests = {
            window.name: FakeManifest(
                2, instrument_id, window.name,
                window.start.isoformat().replace("+00:00", "Z"),
                window.end.isoformat().replace("+00:00", "Z"),
                len(split_data[window.name]), 0,
                split_data[window.name][0].ts_event,
                split_data[window.name][-1].ts_event,
                {"data/state.parquet": "a" * 64},
                "fast", 60, 0, 0,
            )
            for window in DISCOVERY_FOLDS
        }

        def fake_split(_root, split, _instrument):
            return Path("unused") / split, manifests[split]

        def fake_loader(path, _instrument):
            return split_data[path.name], [], []

        with patch("evolution.coverage.discovery_split", side_effect=fake_split):
            report = build_discovery_coverage_report(
                instrument_id,
                Path("unused"),
                split_loader=fake_loader,
            )

        self.assertTrue(report["discovery_only"])
        self.assertEqual(report["splits"], [f"discovery_{i}" for i in range(1, 6)])
        self.assertNotIn("validation", report["splits"])
        fold = report["folds"][0]
        self.assertEqual(fold["manifest_identity"]["split"], "discovery_1")
        self.assertEqual(fold["execution_profile"]["name"], "fast")
        self.assertEqual(fold["label_availability"]["15"]["available_count"], 46)
        self.assertEqual(fold["label_availability"]["30"]["available_count"], 31)
        self.assertEqual(fold["label_availability"]["60"]["available_count"], 1)
        self.assertTrue(fold["feature_readiness"]["ready"])

    def test_past_return_features_are_checked_for_missing_values(self):
        from evolution.coverage import _feature_report

        state = SimpleNamespace(
            close=100.0,
            return_5m=0.0,
            return_15m=None,
            return_60m=None,
        )
        report = _feature_report([(60_000_000_000, state, 0)])
        self.assertEqual(report["fields"]["return_5m"]["finite_count"], 1)
        for name in ("return_15m", "return_60m"):
            self.assertEqual(report["fields"][name]["missing_count"], 1)
            self.assertFalse(report["fields"][name]["ready"])
        self.assertFalse(report["ready"])

    def test_invalid_timestamp_values_are_reported(self):
        from evolution.coverage import _timestamp_entries

        values = [
            SimpleNamespace(ts_event=None),
            SimpleNamespace(ts_event="not-a-timestamp"),
            SimpleNamespace(ts_event=float("nan")),
            SimpleNamespace(ts_event=-1),
        ]
        valid, invalid = _timestamp_entries(values)
        self.assertEqual(valid, [])
        self.assertEqual(
            [item["reason"] for item in invalid],
            ["missing timestamp", "invalid timestamp", "non-finite timestamp", "timestamp is negative"],
        )

    def test_invalid_timestamp_gap_and_nonfinite_feature_are_reported(self):
        from evolution.coverage import _fold_report
        from evolution.spec import Window, utc

        window = Window(
            "discovery_test",
            utc("1970-01-01T00:00:00Z"),
            utc("1970-01-01T01:01:00Z"),
            60,
            0,
        )
        states = self._fold_states(0, 3)
        states[1].ts_event = None
        states[2].ts_event = 180_000_000_000
        states[0].close = float("nan")
        manifest = FakeManifest(
            2, "BTCUSDT.BINANCE", "discovery_test",
            "1970-01-01T00:00:00Z", "1970-01-01T01:01:00Z",
            3, 59, 60_000_000_000, 180_000_000_000, {},
        )

        report = _fold_report(window, manifest, states)
        timestamps = report["state_timestamps"]
        self.assertEqual(timestamps["invalid_timestamp_count"], 1)
        self.assertEqual(timestamps["missing_bucket_count"], 59)
        self.assertFalse(timestamps["continuous"])
        self.assertEqual(report["feature_readiness"]["fields"]["close"]["nonfinite_count"], 1)
        self.assertFalse(report["feature_readiness"]["ready"])
        self.assertEqual(
            report["label_availability"]["15"]["unavailable_reasons"],
            {"missing_target": 1, "nonfinite_close": 1},
        )

    def test_report_requests_only_registered_discovery_folds(self):
        from evolution.coverage import build_discovery_coverage_report

        requested = []

        def forbidden_split(_root, split, _instrument):
            requested.append(split)
            raise ValueError("synthetic missing split")

        with patch("evolution.coverage.discovery_split", side_effect=forbidden_split):
            build_discovery_coverage_report("BTCUSDT.BINANCE", Path("unused"))
        self.assertEqual(requested, [f"discovery_{i}" for i in range(1, 6)])
        self.assertNotIn("validation", requested)
        self.assertNotIn("holdout", requested)

    def test_supplemental_audit_guards_dates_and_manifest_before_loader(self):
        from evolution.coverage import build_supplemental_coverage_report

        loader = unittest.mock.Mock(side_effect=AssertionError("loader called"))
        with patch("evolution.coverage.verify_manifest", side_effect=AssertionError("manifest called")):
            with self.assertRaisesRegex(ValueError, "does not match UTC bounds"):
                build_supplemental_coverage_report(
                    "BTCUSDT.BINANCE",
                    "wrong-name",
                    __import__("datetime").datetime(2026, 8, 29, tzinfo=__import__("datetime").UTC),
                    __import__("datetime").datetime(2026, 8, 30, tzinfo=__import__("datetime").UTC),
                    Path("unused"),
                    split_loader=loader,
                    now=__import__("datetime").datetime(2026, 9, 5, tzinfo=__import__("datetime").UTC),
                )
        loader.assert_not_called()

    def test_quote_quality_reports_duplicates_gaps_crossed_nonfinite_and_boundaries(self):
        from evolution.coverage import build_fold_coverage_report
        from evolution.spec import Window, utc

        window = Window(
            "discovery_supplemental_20260829_20260830",
            utc("2026-08-29T00:00:00Z"),
            utc("2026-08-29T00:00:05Z"),
            1,
            1,
        )
        manifest = FakeManifest(
            2, "BTCUSDT.BINANCE", window.name,
            "2026-08-29T00:00:00Z", "2026-08-29T00:00:05Z",
            0, 5, None, None, {}, "executable", 1, 1, 4,
        )
        start = int(window.start.timestamp() * 1_000_000_000)
        quotes = [
            QuoteRow(start + 1_000_000_000, "BTCUSDT.BINANCE", 99, 101, 100, 2, 200),
            QuoteRow(start + 1_000_000_000, "BTCUSDT.BINANCE", 99, 101, 100, 2, 200),
            QuoteRow(start + 3_000_000_000, "BTCUSDT.BINANCE", 102, 101, 101.5, -1, -99),
            QuoteRow(start + 4_000_000_000, "BTCUSDT.BINANCE", float("nan"), 101, float("nan"), float("nan"), float("nan")),
            QuoteRow(start, "BTCUSDT.BINANCE", 99, 101, 100, 2, 200),
        ]
        report = build_fold_coverage_report(window, manifest, [], quotes)
        quality = report["quote_quality"]
        self.assertEqual(quality["duplicate_timestamp_count"], 1)
        self.assertEqual(quality["expected_sample_count"], 5)
        self.assertEqual(quality["missing_second_count"], 2)
        self.assertEqual(quality["crossed_count"], 1)
        self.assertEqual(quality["nonfinite_count"], 1)
        self.assertEqual(quality["boundary_violation_count"], 1)
        self.assertEqual(quality["timestamp_alignment_violation_count"], 0)

    def test_price_efficiency_flat_monotonic_and_oscillating(self):
        from evolution.coverage import _price_efficiency_distribution

        def entries(closes):
            return [
                (index * 60_000_000_000, SimpleNamespace(close=close), index)
                for index, close in enumerate(closes, start=1)
            ]

        flat = _price_efficiency_distribution(entries([100.0] * 61), "1970-01-01")
        monotonic = _price_efficiency_distribution(entries([float(index) for index in range(61)]), "1970-01-01")
        oscillating = _price_efficiency_distribution(
            entries([100.0 + (index % 2) for index in range(61)]),
            "1970-01-01",
        )
        self.assertEqual(flat["undefined_denominator_count"], 1)
        self.assertEqual(monotonic["median"], 1.0)
        self.assertEqual(oscillating["median"], 0.0)

    def test_output_is_written_without_loading_remote_catalog(self):
        from evolution.coverage import run_discovery_coverage_diagnostic

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "coverage.json"
            with patch("evolution.coverage.build_discovery_coverage_report", return_value={"discovery_only": True}):
                result = run_discovery_coverage_diagnostic(
                    "BTCUSDT.BINANCE", Path(directory), output,
                )
            self.assertEqual(result, {"discovery_only": True})
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), result)

    @staticmethod
    def _fold_states(start_ns: int, count: int) -> list[SimpleNamespace]:
        from evolution.coverage import FEATURE_FIELDS

        states = []
        for index in range(count):
            values = {name: 1.0 for name in FEATURE_FIELDS}
            values.update(
                instrument_id="BTCUSDT.BINANCE",
                ts_event=start_ns + (index + 1) * 60_000_000_000,
                ts_init=start_ns + (index + 1) * 60_000_000_000 + 2,
                close=100.0,
            )
            states.append(SimpleNamespace(**values))
        return states


if __name__ == "__main__":
    unittest.main()
