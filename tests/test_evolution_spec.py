import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


class EvolutionSpecTests(unittest.TestCase):
    def test_splits_follow_verified_catalog_coverage_without_overlap(self):
        from evolution.spec import ALL_WINDOWS
        from evolution.spec import DISCOVERY_FOLDS

        self.assertEqual(len(DISCOVERY_FOLDS), 5)
        for previous, current in zip(ALL_WINDOWS, ALL_WINDOWS[1:]):
            self.assertEqual(previous.end, current.start)
        self.assertEqual(ALL_WINDOWS[0].start.isoformat(), "2026-06-13T00:00:00+00:00")
        self.assertEqual(ALL_WINDOWS[-1].end.isoformat(), "2026-07-25T00:00:00+00:00")
        self.assertEqual([window.quote_interval_seconds for window in DISCOVERY_FOLDS], [60] * 5)
        self.assertEqual(ALL_WINDOWS[-1].execution_delay_seconds, 1)

    def test_three_instruments_have_fixed_precision_and_fees(self):
        from evolution.instruments import build_instrument

        expected = {"BTCUSDT.BINANCE": 5, "ETHUSDT.BINANCE": 4, "BNBUSDT.BINANCE": 3}
        for instrument_id, precision in expected.items():
            instrument = build_instrument(instrument_id)
            self.assertEqual(instrument.price_precision, 2)
            self.assertEqual(instrument.size_precision, precision)
            self.assertEqual(instrument.maker_fee, Decimal("0.001"))
            self.assertEqual(instrument.taker_fee, Decimal("0.001"))

    def test_run_directories_are_instrument_isolated(self):
        from evolution.spec import run_directory

        root = Path("outputs/evolution")
        paths = {run_directory(root, instrument, "run") for instrument in (
            "BTCUSDT.BINANCE", "ETHUSDT.BINANCE", "BNBUSDT.BINANCE"
        )}
        self.assertEqual(len(paths), 3)
        self.assertTrue(all(path.parent.name in {"btcusdt", "ethusdt", "bnbusdt"} for path in paths))


if __name__ == "__main__":
    unittest.main()
