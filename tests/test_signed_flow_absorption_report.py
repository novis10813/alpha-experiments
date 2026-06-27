import tempfile
import unittest
from pathlib import Path


class SignedFlowAbsorptionReportTests(unittest.TestCase):
    def test_build_absorption_context_summarizes_four_regimes(self):
        from reports.signed_flow_absorption_report import build_absorption_context

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.8",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.8",
                        "3000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.8",
                        "4000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.8",
                    ],
                ),
                encoding="utf-8",
            )
            feature_path = Path(directory) / "features.csv"
            feature_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price,volume,trade_count,buy_trade_count,sell_trade_count,"
                        "buy_volume,sell_volume,signed_trade_count,signed_volume,trade_imbalance,volume_imbalance",
                        "1000000000,BTCUSDT.BINANCE,100,1,1,1,0,1,0,1,1,1,1",
                        "2000000000,BTCUSDT.BINANCE,101,1,1,0,1,0,1,-1,-1,-1,-1",
                        "3000000000,BTCUSDT.BINANCE,102,1,1,0,1,0,1,-1,-1,-1,-1",
                        "4000000000,BTCUSDT.BINANCE,103,1,1,1,0,1,0,1,1,1,1",
                        "5000000000,BTCUSDT.BINANCE,104,1,1,1,0,1,0,1,1,1,1",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_absorption_context(
                alpha_path,
                feature_path,
                horizons_seconds=[1],
                book_threshold=0.5,
                flow_threshold=0.0,
            )

        self.assertEqual(context.instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(context.horizons_seconds, [1])
        self.assertEqual(context.joined_count, 4)
        self.assertEqual(len(context.regime_summaries), 4)
        self.assertEqual(
            {summary.regime for summary in context.regime_summaries},
            {
                "bid_heavy_buy_flow",
                "ask_heavy_sell_flow",
                "bid_heavy_sell_flow",
                "ask_heavy_buy_flow",
            },
        )
        confirmed = next(
            summary
            for summary in context.regime_summaries
            if summary.regime == "bid_heavy_buy_flow"
        )
        self.assertEqual(confirmed.interpretation, "confirmed_demand_pressure")
        self.assertEqual(confirmed.count, 1)

    def test_render_absorption_report_html_contains_summary_data(self):
        from reports.signed_flow_absorption_report import build_absorption_context
        from reports.signed_flow_absorption_report import render_absorption_report_html

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.8",
                    ],
                ),
                encoding="utf-8",
            )
            feature_path = Path(directory) / "features.csv"
            feature_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price,volume,trade_count,buy_trade_count,sell_trade_count,"
                        "buy_volume,sell_volume,signed_trade_count,signed_volume,trade_imbalance,volume_imbalance",
                        "1000000000,BTCUSDT.BINANCE,100,1,1,1,0,1,0,1,1,1,1",
                        "2000000000,BTCUSDT.BINANCE,101,1,1,1,0,1,0,1,1,1,1",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_absorption_context(alpha_path, feature_path, horizons_seconds=[1])
            html = render_absorption_report_html(context)

        self.assertIn("Signed Flow Absorption Report", html)
        self.assertIn("regimeSummaries", html)
        self.assertIn("bid_heavy_buy_flow", html)
        self.assertIn("Plotly.newPlot", html)


if __name__ == "__main__":
    unittest.main()
