import tempfile
import unittest
from pathlib import Path


class DenseSignedFlowReportTests(unittest.TestCase):
    def test_build_dense_signed_flow_context_summarizes_density_and_flow_regimes(self):
        from reports.dense_signed_flow_report import build_dense_signed_flow_context

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
                        "2000000000,BTCUSDT.BINANCE,101,1,2,0,1,0,1,-1,-1,-1,-1",
                        "3000000000,BTCUSDT.BINANCE,102,1,20,0,1,0,1,-1,-1,-1,-1",
                        "4000000000,BTCUSDT.BINANCE,103,1,30,1,0,1,0,1,1,1,1",
                        "5000000000,BTCUSDT.BINANCE,104,1,30,1,0,1,0,1,1,1,1",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_dense_signed_flow_context(
                alpha_path,
                feature_path,
                horizons_seconds=[1],
                book_threshold=0.5,
                flow_threshold=0.0,
            )

        self.assertEqual(context.instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(context.alpha_name, "orderbook_imbalance_depth10")
        self.assertEqual(context.density_threshold, 11.0)
        self.assertEqual(context.joined_count, 4)
        self.assertEqual(
            {summary.density_regime for summary in context.summaries},
            {"density_low", "density_high"},
        )
        self.assertEqual(
            {summary.flow_regime for summary in context.summaries},
            {
                "bid_heavy_buy_flow",
                "ask_heavy_sell_flow",
                "bid_heavy_sell_flow",
                "ask_heavy_buy_flow",
            },
        )
        high_absorption = next(
            summary
            for summary in context.summaries
            if summary.density_regime == "density_high"
            and summary.flow_regime == "bid_heavy_sell_flow"
        )
        self.assertEqual(high_absorption.count, 1)
        self.assertEqual(high_absorption.interpretation, "bid_absorption")

    def test_render_dense_signed_flow_report_html_contains_summary_data(self):
        from reports.dense_signed_flow_report import build_dense_signed_flow_context
        from reports.dense_signed_flow_report import render_dense_signed_flow_report_html

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

            context = build_dense_signed_flow_context(alpha_path, feature_path, horizons_seconds=[1])
            html = render_dense_signed_flow_report_html(context)

        self.assertIn("Dense Signed Flow Report", html)
        self.assertIn("denseFlowSummaries", html)
        self.assertIn("directional return", html)


if __name__ == "__main__":
    unittest.main()
