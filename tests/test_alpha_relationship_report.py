import tempfile
import unittest
from pathlib import Path


class AlphaRelationshipReportTests(unittest.TestCase):
    def test_build_relationship_context_computes_forward_returns_from_price_csv(self):
        from reports.alpha_relationship_report import build_relationship_context

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.5",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.5",
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
                        "2000000000,BTCUSDT.BINANCE,102",
                        "3000000000,BTCUSDT.BINANCE,101",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_relationship_context(
                alpha_path,
                price_path,
                horizons_seconds=[1],
                bucket_count=2,
            )

        self.assertEqual(context.instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(context.alpha_name, "orderbook_imbalance_depth10")
        self.assertEqual(context.horizons_seconds, [1])
        self.assertEqual(len(context.forward_return_points), 2)
        self.assertEqual(context.forward_return_points[0].current_price, 100)
        self.assertEqual(context.forward_return_points[0].future_price, 102)
        self.assertAlmostEqual(context.forward_return_points[0].forward_return, 0.02)
        self.assertAlmostEqual(
            context.forward_return_points[1].forward_return,
            (101 / 102) - 1,
        )

    def test_build_relationship_context_summarizes_forward_returns_by_alpha_bucket(self):
        from reports.alpha_relationship_report import build_relationship_context

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
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
            price_path = Path(directory) / "prices.csv"
            price_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price",
                        "1000000000,BTCUSDT.BINANCE,100",
                        "2000000000,BTCUSDT.BINANCE,101",
                        "3000000000,BTCUSDT.BINANCE,102",
                        "4000000000,BTCUSDT.BINANCE,103",
                        "5000000000,BTCUSDT.BINANCE,104",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_relationship_context(
                alpha_path,
                price_path,
                horizons_seconds=[1],
                bucket_count=2,
            )

        self.assertEqual(len(context.bucket_summaries), 2)
        self.assertEqual(context.bucket_summaries[0].count, 2)
        self.assertEqual(context.bucket_summaries[0].min_alpha, -0.75)
        self.assertEqual(context.bucket_summaries[0].max_alpha, -0.25)
        self.assertEqual(context.bucket_summaries[1].min_alpha, 0.25)
        self.assertEqual(context.bucket_summaries[1].max_alpha, 0.75)
        self.assertEqual(context.bucket_summaries[0].positive_rate, 1.0)

    def test_render_relationship_report_html_contains_scatter_and_bucket_data(self):
        from reports.alpha_relationship_report import build_relationship_context
        from reports.alpha_relationship_report import render_relationship_report_html

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.5",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.5",
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
                        "3000000000,BTCUSDT.BINANCE,102",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_relationship_context(
                alpha_path,
                price_path,
                horizons_seconds=[1],
                bucket_count=2,
            )
            html = render_relationship_report_html(context)

        self.assertIn("Order Book Imbalance Relationship", html)
        self.assertIn("forwardReturnPoints", html)
        self.assertIn("bucketSummaries", html)
        self.assertIn('name: "forward return"', html)
        self.assertIn('name: "bucket mean"', html)

    def test_build_relationship_context_rejects_sparse_price_data_for_short_horizon(self):
        from reports.alpha_relationship_report import build_relationship_context

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.5",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.5",
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
                        "61000000000,BTCUSDT.BINANCE,101",
                        "121000000000,BTCUSDT.BINANCE,102",
                    ],
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "too sparse"):
                build_relationship_context(
                    alpha_path,
                    price_path,
                    horizons_seconds=[10],
                    bucket_count=2,
                )


if __name__ == "__main__":
    unittest.main()
