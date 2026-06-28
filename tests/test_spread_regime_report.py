import tempfile
import unittest
from pathlib import Path


class SpreadRegimeReportTests(unittest.TestCase):
    def test_build_spread_regime_context_summarizes_spread_groups(self):
        from reports.spread_regime_report import build_spread_regime_context

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,1.0",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,1.0",
                        "3000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-1.0",
                        "4000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-1.0",
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
                        "2000000000,BTCUSDT.BINANCE,102,103,102.5,1,20",
                        "3000000000,BTCUSDT.BINANCE,104,105,104.5,1,30",
                        "4000000000,BTCUSDT.BINANCE,106,107,106.5,1,40",
                        "5000000000,BTCUSDT.BINANCE,108,109,108.5,1,40",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_spread_regime_context(
                alpha_path,
                quote_path,
                horizons_seconds=[1],
                delay_seconds=0,
                cost_bps=2,
            )

        self.assertEqual(context.instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(context.alpha_name, "orderbook_imbalance_depth10")
        self.assertEqual(context.spread_median_bps, 25)
        self.assertEqual(context.spread_p75_bps, 32.5)
        self.assertEqual(context.spread_p90_bps, 37)
        self.assertEqual(
            {summary.regime for summary in context.summaries},
            {"spread_low", "spread_high", "spread_top_quartile", "spread_top_decile", "spread_below_top_decile"},
        )
        self.assertEqual(
            next(summary for summary in context.summaries if summary.regime == "spread_low").count,
            2,
        )
        self.assertEqual(
            next(summary for summary in context.summaries if summary.regime == "spread_top_decile").count,
            1,
        )

    def test_render_spread_regime_report_html_contains_summary_data(self):
        from reports.spread_regime_report import build_spread_regime_context
        from reports.spread_regime_report import render_spread_regime_report_html

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,1.0",
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
            context = build_spread_regime_context(alpha_path, quote_path, horizons_seconds=[1])
            html = render_spread_regime_report_html(context)

        self.assertIn("Spread Regime Report", html)
        self.assertIn("spreadSummaries", html)
        self.assertIn("mean net executable return", html)


if __name__ == "__main__":
    unittest.main()
