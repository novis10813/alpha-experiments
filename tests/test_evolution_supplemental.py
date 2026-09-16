import tempfile
import unittest
from datetime import UTC
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from evolution.supplemental import parse_utc_day


class EvolutionSupplementalTests(unittest.TestCase):
    def test_rejects_invalid_dates_before_catalog_call(self):
        from evolution.supplemental import build_supplemental_discovery

        cases = (
            ("2026-07-11", "2026-07-13", "protected"),
            ("2026-08-28", "2026-08-29", "quarantined"),
            ("2026-08-29T12:00:00Z", "2026-08-30", "UTC day"),
            ("2026-09-05", "2026-09-06", "completed"),
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch("evolution.dataset.make_catalog", side_effect=AssertionError("catalog called")):
                for start, end, message in cases:
                    with self.subTest(start=start, end=end):
                        with self.assertRaisesRegex(ValueError, message):
                            build_supplemental_discovery(
                                "BTCUSDT.BINANCE",
                                parse_utc_day(start, "--start"),
                                parse_utc_day(end, "--end"),
                                Path(directory),
                                now=datetime(2026, 9, 5, tzinfo=UTC),
                            )

    def test_delegates_to_readonly_window_builder_with_executable_profile(self):
        from evolution.spec import EXECUTABLE_DISCOVERY_PROFILE
        from evolution.supplemental import build_supplemental_discovery

        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            with patch("evolution.supplemental.build_window_from_catalog") as builder:
                manifest = build_supplemental_discovery(
                    "BTCUSDT.BINANCE",
                    datetime(2026, 8, 29, tzinfo=UTC),
                    datetime(2026, 8, 30, tzinfo=UTC),
                    output_root,
                    now=datetime(2026, 9, 5, tzinfo=UTC),
                )

        builder.assert_called_once()
        instrument_id, window, root = builder.call_args.args
        self.assertEqual(instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(root, output_root)
        self.assertEqual(window.name, "discovery_supplemental_20260829_20260830")
        self.assertEqual(window.start.isoformat(), "2026-08-29T00:00:00+00:00")
        self.assertEqual(window.end.isoformat(), "2026-08-30T00:00:00+00:00")
        self.assertEqual(window.quote_interval_seconds, 1)
        self.assertEqual(window.execution_delay_seconds, 1)
        self.assertEqual(builder.call_args.kwargs["profile"], EXECUTABLE_DISCOVERY_PROFILE)
        self.assertIsInstance(manifest, unittest.mock.Mock)

    def test_existing_target_is_rejected_without_writing_or_building(self):
        from evolution.supplemental import build_supplemental_discovery

        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            target = output_root / "discovery_supplemental_20260829_20260830" / "BTCUSDT.BINANCE"
            target.mkdir(parents=True)
            snapshot = target / "snapshot.txt"
            snapshot.write_text("preserve", encoding="utf-8")
            with patch("evolution.supplemental.build_window_from_catalog") as builder:
                with self.assertRaisesRegex(RuntimeError, "already exists"):
                    build_supplemental_discovery(
                        "BTCUSDT.BINANCE",
                        datetime(2026, 8, 29, tzinfo=UTC),
                        datetime(2026, 8, 30, tzinfo=UTC),
                        output_root,
                        now=datetime(2026, 9, 5, tzinfo=UTC),
                    )
            builder.assert_not_called()
            self.assertEqual(snapshot.read_text(encoding="utf-8"), "preserve")

    def test_split_name_is_not_a_registered_discovery_fold(self):
        from evolution.supplemental import supplemental_split_name

        name = supplemental_split_name(
            datetime(2026, 8, 29, tzinfo=UTC),
            datetime(2026, 8, 30, tzinfo=UTC),
        )
        self.assertEqual(name, "discovery_supplemental_20260829_20260830")
        self.assertNotIn(name, {f"discovery_{index}" for index in range(1, 6)})


if __name__ == "__main__":
    unittest.main()
