import tempfile
import unittest
from pathlib import Path


class ExtremeImbalanceReportTests(unittest.TestCase):
    def test_build_extreme_context_summarizes_positive_and_negative_events(self):
        from reports.extreme_imbalance_report import build_extreme_context

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.96",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.97",
                        "3000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.10",
                    ],
                ),
                encoding="utf-8",
            )
            price_path = Path(directory) / "prices.csv"
            price_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price",
                        "1000000000,BTCUSDT.BINANCE,100",
                        "2000000000,BTCUSDT.BINANCE,101",
                        "3000000000,BTCUSDT.BINANCE,99",
                        "4000000000,BTCUSDT.BINANCE,98",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_extreme_context(
                alpha_path,
                price_path,
                thresholds=[0.95],
                horizons_seconds=[1, 2],
            )

        self.assertEqual(context.instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(context.alpha_name, "orderbook_imbalance_depth10")
        self.assertEqual(len(context.summaries), 4)
        positive_1s = next(
            summary
            for summary in context.summaries
            if summary.side == "positive" and summary.horizon_seconds == 1
        )
        negative_1s = next(
            summary
            for summary in context.summaries
            if summary.side == "negative" and summary.horizon_seconds == 1
        )
        self.assertEqual(positive_1s.count, 1)
        self.assertAlmostEqual(positive_1s.mean_forward_return, 0.01)
        self.assertAlmostEqual(positive_1s.mean_directional_return, 0.01)
        self.assertAlmostEqual(negative_1s.mean_forward_return, (99 / 101) - 1)
        self.assertAlmostEqual(negative_1s.mean_directional_return, 1 - (99 / 101))
        self.assertEqual(negative_1s.directional_hit_rate, 1.0)

    def test_render_extreme_report_html_contains_path_and_summary_data(self):
        from reports.extreme_imbalance_report import build_extreme_context
        from reports.extreme_imbalance_report import render_extreme_report_html

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.96",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.97",
                    ],
                ),
                encoding="utf-8",
            )
            price_path = Path(directory) / "prices.csv"
            price_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price",
                        "1000000000,BTCUSDT.BINANCE,100",
                        "2000000000,BTCUSDT.BINANCE,101",
                        "3000000000,BTCUSDT.BINANCE,99",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_extreme_context(
                alpha_path,
                price_path,
                thresholds=[0.95],
                horizons_seconds=[1],
            )
            html = render_extreme_report_html(context)

        self.assertIn("Extreme Imbalance Event Study", html)
        self.assertIn("summaryRows", html)
        self.assertIn("mean directional return", html)
        self.assertIn("Plotly.newPlot", html)

    def test_build_extreme_context_accepts_small_price_timestamp_jitter(self):
        from reports.extreme_imbalance_report import build_extreme_context

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.96",
                    ],
                ),
                encoding="utf-8",
            )
            price_path = Path(directory) / "prices.csv"
            price_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price",
                        "1000000000,BTCUSDT.BINANCE,100",
                        "2100000000,BTCUSDT.BINANCE,101",
                        "3200000000,BTCUSDT.BINANCE,102",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_extreme_context(
                alpha_path,
                price_path,
                thresholds=[0.95],
                horizons_seconds=[1],
            )

        self.assertEqual(context.summaries[0].count, 1)


if __name__ == "__main__":
    unittest.main()
