import tempfile
import unittest
from pathlib import Path


class ExecutableReturnReportTests(unittest.TestCase):
    def test_build_context_uses_bid_ask_execution_for_long_short_and_flat(self):
        from reports.executable_return_report import build_executable_return_context

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.8",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.8",
                        "3000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.0",
                    ],
                ),
                encoding="utf-8",
            )
            quote_path = Path(directory) / "quotes.csv"
            quote_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,bid,ask,mid,spread,spread_bps",
                        "1000000000,BTCUSDT.BINANCE,100,101,100.5,1,99.50248756218906",
                        "2000000000,BTCUSDT.BINANCE,103,104,103.5,1,96.6183574879227",
                        "3000000000,BTCUSDT.BINANCE,98,99,98.5,1,101.5228426395939",
                        "4000000000,BTCUSDT.BINANCE,110,111,110.5,1,90.49773755656108",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_executable_return_context(
                alpha_path,
                quote_path,
                horizons_seconds=[1],
                delay_seconds=[0],
                cost_bps=[0],
            )

        points = context.points
        self.assertEqual(len(points), 3)
        self.assertAlmostEqual(points[0].gross_return, (103 / 101) - 1)
        self.assertAlmostEqual(points[1].gross_return, (103 / 99) - 1)
        self.assertEqual(points[2].gross_return, 0.0)
        self.assertEqual(points[2].side, 0)

    def test_build_context_applies_delay_and_cost(self):
        from reports.executable_return_report import build_executable_return_context

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
                        "1000000000,BTCUSDT.BINANCE,100,101,100.5,1,99.50248756218906",
                        "2000000000,BTCUSDT.BINANCE,105,106,105.5,1,94.7867298578199",
                        "3000000000,BTCUSDT.BINANCE,109,110,109.5,1,91.324200913242",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_executable_return_context(
                alpha_path,
                quote_path,
                horizons_seconds=[1],
                delay_seconds=[1],
                cost_bps=[2],
            )

        point = context.points[0]
        self.assertEqual(point.entry_ts_event, 2_000_000_000)
        self.assertEqual(point.exit_ts_event, 3_000_000_000)
        self.assertAlmostEqual(point.gross_return, (109 / 106) - 1)
        self.assertAlmostEqual(point.net_return, ((109 / 106) - 1) - 0.0002)

    def test_build_context_summarizes_by_horizon_delay_and_cost(self):
        from reports.executable_return_report import build_executable_return_context

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,1.0",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,1.0",
                    ],
                ),
                encoding="utf-8",
            )
            quote_path = Path(directory) / "quotes.csv"
            quote_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,bid,ask,mid,spread,spread_bps",
                        "1000000000,BTCUSDT.BINANCE,100,101,100.5,1,99.50248756218906",
                        "2000000000,BTCUSDT.BINANCE,102,103,102.5,1,97.5609756097561",
                        "3000000000,BTCUSDT.BINANCE,104,105,104.5,1,95.69377990430622",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_executable_return_context(
                alpha_path,
                quote_path,
                horizons_seconds=[1],
                delay_seconds=[0],
                cost_bps=[0, 2],
            )

        self.assertEqual(len(context.summaries), 2)
        self.assertEqual(context.summaries[0].count, 2)
        self.assertGreater(context.summaries[0].mean_gross_return, context.summaries[1].mean_net_return)

    def test_render_executable_return_report_html_contains_summary_data(self):
        from reports.executable_return_report import build_executable_return_context
        from reports.executable_return_report import render_executable_return_report_html

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
                        "1000000000,BTCUSDT.BINANCE,100,101,100.5,1,99.50248756218906",
                        "2000000000,BTCUSDT.BINANCE,102,103,102.5,1,97.5609756097561",
                    ],
                ),
                encoding="utf-8",
            )
            context = build_executable_return_context(
                alpha_path,
                quote_path,
                horizons_seconds=[1],
                delay_seconds=[0],
                cost_bps=[0],
            )
            html = render_executable_return_report_html(context)

        self.assertIn("Executable Return Screen", html)
        self.assertIn("summaries", html)
        self.assertIn("mean net executable return", html)


if __name__ == "__main__":
    unittest.main()
