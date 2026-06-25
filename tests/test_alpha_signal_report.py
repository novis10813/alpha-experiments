import tempfile
import unittest
from pathlib import Path


class AlphaSignalReportTests(unittest.TestCase):
    def test_build_report_context_summarizes_and_downsamples_signal_csv(self):
        from reports.alpha_signal_report import build_report_context

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "alpha.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.75",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.25",
                        "3000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.25",
                        "4000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.75",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_report_context(csv_path, max_points=2, threshold=0.5)

        self.assertEqual(context.row_count, 4)
        self.assertEqual(context.instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(context.alpha_name, "orderbook_imbalance_depth10")
        self.assertEqual(context.min_value, -0.75)
        self.assertEqual(context.max_value, 0.75)
        self.assertEqual(len(context.series_points), 2)
        self.assertEqual(len(context.positive_events), 1)
        self.assertEqual(len(context.negative_events), 1)
        self.assertEqual(len(context.histogram), len(context.histogram_bins))
        self.assertGreater(context.histogram_bins[0], -0.75)
        self.assertLess(context.histogram_bins[-1], 0.75)

    def test_render_report_html_contains_chart_data_and_threshold(self):
        from reports.alpha_signal_report import build_report_context
        from reports.alpha_signal_report import render_report_html

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "alpha.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.75",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.75",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_report_context(csv_path, threshold=0.5)
            html = render_report_html(context)

        self.assertIn("Order Book Imbalance", html)
        self.assertIn("BTCUSDT.BINANCE", html)
        self.assertIn("threshold: 0.5", html)
        self.assertIn("seriesPoints", html)

    def test_render_report_html_uses_plotly_for_interactive_charts(self):
        from reports.alpha_signal_report import build_report_context
        from reports.alpha_signal_report import render_report_html

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "alpha.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.75",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.75",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_report_context(csv_path, threshold=0.5)
            html = render_report_html(context)

        self.assertIn("plotly", html.lower())
        self.assertIn("Plotly.newPlot", html)
        self.assertIn('type: "linear"', html)
        self.assertNotIn("<canvas", html)

    def test_render_report_html_uses_time_range_slider_instead_of_box_select(self):
        from reports.alpha_signal_report import build_report_context
        from reports.alpha_signal_report import render_report_html

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "alpha.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.75",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.75",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_report_context(csv_path, threshold=0.5)
            html = render_report_html(context)

        self.assertIn('dragmode: "pan"', html)
        self.assertIn("rangeslider", html)
        self.assertIn('visible: true', html)
        self.assertIn('"zoom2d"', html)
        self.assertIn('"select2d"', html)
        self.assertIn('"lasso2d"', html)

    def test_build_report_context_accepts_price_overlay_csv(self):
        from reports.alpha_signal_report import build_report_context

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "alpha.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.75",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.75",
                    ],
                ),
                encoding="utf-8",
            )
            price_path = Path(directory) / "price.csv"
            price_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price",
                        "1000000000,BTCUSDT.BINANCE,100.25",
                        "2000000000,BTCUSDT.BINANCE,101.50",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_report_context(csv_path, price_path=price_path)

        self.assertEqual(context.price_source_path, price_path)
        self.assertEqual(len(context.price_points), 2)
        self.assertEqual(context.price_points[0].value, 100.25)

    def test_render_report_html_includes_price_overlay_on_secondary_axis(self):
        from reports.alpha_signal_report import build_report_context
        from reports.alpha_signal_report import render_report_html

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "alpha.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.75",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.75",
                    ],
                ),
                encoding="utf-8",
            )
            price_path = Path(directory) / "price.csv"
            price_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price",
                        "1000000000,BTCUSDT.BINANCE,100.25",
                        "2000000000,BTCUSDT.BINANCE,101.50",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_report_context(csv_path, price_path=price_path)
            html = render_report_html(context)

        self.assertIn("pricePoints", html)
        self.assertIn('name: "trade price"', html)
        self.assertIn("yaxis2", html)


if __name__ == "__main__":
    unittest.main()
