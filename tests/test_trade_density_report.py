import tempfile
import unittest
from pathlib import Path


class TradeDensityReportTests(unittest.TestCase):
    def test_build_density_context_summarizes_low_and_high_density_regimes(self):
        from reports.trade_density_report import build_density_context

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.8",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.2",
                        "3000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.2",
                        "4000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.8",
                    ],
                ),
                encoding="utf-8",
            )
            feature_path = Path(directory) / "features.csv"
            feature_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price,volume,trade_count",
                        "1000000000,BTCUSDT.BINANCE,100,1,1",
                        "2000000000,BTCUSDT.BINANCE,101,1,2",
                        "3000000000,BTCUSDT.BINANCE,102,1,20",
                        "4000000000,BTCUSDT.BINANCE,104,1,30",
                        "5000000000,BTCUSDT.BINANCE,106,1,30",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_density_context(
                alpha_path,
                feature_path,
                horizons_seconds=[1],
                bucket_count=2,
            )

        self.assertEqual(context.instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(context.alpha_name, "orderbook_imbalance_depth10")
        self.assertEqual(context.horizons_seconds, [1])
        self.assertEqual(len(context.regime_summaries), 2)
        self.assertEqual({summary.regime for summary in context.regime_summaries}, {"low", "high"})
        self.assertGreater(
            next(summary for summary in context.regime_summaries if summary.regime == "high").density_min,
            next(summary for summary in context.regime_summaries if summary.regime == "low").density_min,
        )

    def test_render_density_report_html_contains_regime_data(self):
        from reports.trade_density_report import build_density_context
        from reports.trade_density_report import render_density_report_html

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.8",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.8",
                    ],
                ),
                encoding="utf-8",
            )
            feature_path = Path(directory) / "features.csv"
            feature_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price,volume,trade_count",
                        "1000000000,BTCUSDT.BINANCE,100,1,1",
                        "2000000000,BTCUSDT.BINANCE,101,1,20",
                        "3000000000,BTCUSDT.BINANCE,102,1,20",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_density_context(
                alpha_path,
                feature_path,
                horizons_seconds=[1],
                bucket_count=2,
            )
            html = render_density_report_html(context)

        self.assertIn("Trade Density Regime Report", html)
        self.assertIn("regimeSummaries", html)
        self.assertIn("Plotly.newPlot", html)


if __name__ == "__main__":
    unittest.main()
