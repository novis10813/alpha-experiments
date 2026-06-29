import tempfile
import unittest
from pathlib import Path


class KbarReturnReportTests(unittest.TestCase):
    def test_build_kbar_context_aggregates_ohlc_and_returns(self):
        from reports.kbar_return_report import build_kbar_context

        with tempfile.TemporaryDirectory() as directory:
            price_path = Path(directory) / "prices.csv"
            price_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price",
                        "10000000000,BTCUSDT.BINANCE,100",
                        "20000000000,BTCUSDT.BINANCE,105",
                        "30000000000,BTCUSDT.BINANCE,98",
                        "70000000000,BTCUSDT.BINANCE,99",
                        "80000000000,BTCUSDT.BINANCE,101",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_kbar_context(price_path, interval_seconds=60)

        self.assertEqual(context.instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(context.interval_seconds, 60)
        self.assertEqual(len(context.bars), 2)
        first, second = context.bars
        self.assertEqual(first.start_time, 0)
        self.assertEqual(first.end_time, 60_000_000_000)
        self.assertEqual(first.instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(first.ts_event, 60_000_000_000)
        self.assertEqual(first.open, 100.0)
        self.assertEqual(first.high, 105.0)
        self.assertEqual(first.low, 98.0)
        self.assertEqual(first.close, 98.0)
        self.assertAlmostEqual(first.bar_return, -0.02)
        self.assertIsNone(first.close_to_close_return)
        self.assertEqual(second.ts_event, 120_000_000_000)
        self.assertAlmostEqual(second.bar_return, 2 / 99)
        self.assertAlmostEqual(second.close_to_close_return, 3 / 98)

    def test_build_kbar_context_rejects_mixed_instruments(self):
        from reports.kbar_return_report import build_kbar_context

        with tempfile.TemporaryDirectory() as directory:
            price_path = Path(directory) / "prices.csv"
            price_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price",
                        "10000000000,BTCUSDT.BINANCE,100",
                        "20000000000,ETHUSDT.BINANCE,2000",
                    ],
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "exactly one instrument_id"):
                build_kbar_context(price_path, interval_seconds=60)

    def test_render_kbar_report_html_contains_scatter_and_violin(self):
        from reports.kbar_return_report import build_kbar_context
        from reports.kbar_return_report import render_kbar_report_html

        with tempfile.TemporaryDirectory() as directory:
            price_path = Path(directory) / "prices.csv"
            price_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price",
                        "10000000000,BTCUSDT.BINANCE,100",
                        "70000000000,BTCUSDT.BINANCE,101",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_kbar_context(price_path, interval_seconds=60)
            html = render_kbar_report_html(context)

        self.assertIn("Kbar Return Distribution", html)
        self.assertIn("barReturn", html)
        self.assertIn("type: \"violin\"", html)
        self.assertIn("Plotly.newPlot", html)


if __name__ == "__main__":
    unittest.main()
