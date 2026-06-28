import tempfile
import unittest
from pathlib import Path


class ClusteredEventReportTests(unittest.TestCase):
    def test_build_clustered_event_context_collapses_consecutive_extremes(self):
        from reports.clustered_event_report import build_clustered_event_context

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.96",
                        "1100000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.97",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.10",
                        "3000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.96",
                        "3100000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.97",
                    ],
                ),
                encoding="utf-8",
            )
            quote_path = Path(directory) / "quotes.csv"
            quote_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,bid,ask,mid,spread,spread_bps",
                        "1000000000,BTCUSDT.BINANCE,100,101,100.5,1,10",
                        "2000000000,BTCUSDT.BINANCE,102,103,102.5,1,10",
                        "3000000000,BTCUSDT.BINANCE,104,105,104.5,1,10",
                        "4000000000,BTCUSDT.BINANCE,98,99,98.5,1,10",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_clustered_event_context(
                alpha_path,
                quote_path,
                thresholds=[0.95],
                horizons_seconds=[1],
                cost_bps=2,
            )

        self.assertEqual(context.instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(context.alpha_name, "orderbook_imbalance_depth10")
        self.assertEqual(context.raw_extreme_count, 4)
        self.assertEqual(context.cluster_count, 2)
        self.assertEqual({summary.side for summary in context.summaries}, {"positive", "negative"})
        self.assertEqual(
            next(summary for summary in context.summaries if summary.side == "positive").count,
            1,
        )

    def test_render_clustered_event_report_html_contains_summary_data(self):
        from reports.clustered_event_report import build_clustered_event_context
        from reports.clustered_event_report import render_clustered_event_report_html

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
            quote_path = Path(directory) / "quotes.csv"
            quote_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,bid,ask,mid,spread,spread_bps",
                        "1000000000,BTCUSDT.BINANCE,100,101,100.5,1,10",
                        "2000000000,BTCUSDT.BINANCE,102,103,102.5,1,10",
                    ],
                ),
                encoding="utf-8",
            )
            context = build_clustered_event_context(alpha_path, quote_path, horizons_seconds=[1])
            html = render_clustered_event_report_html(context)

        self.assertIn("Clustered Extreme Imbalance Report", html)
        self.assertIn("clusterSummaries", html)
        self.assertIn("mean net executable return", html)


if __name__ == "__main__":
    unittest.main()
