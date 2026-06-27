import tempfile
import unittest
from pathlib import Path


class VolumeInteractionReportTests(unittest.TestCase):
    def test_build_volume_interaction_context_compares_raw_and_volume_adjusted_signal(self):
        from reports.volume_interaction_report import build_volume_interaction_context

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "1000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.5",
                        "2000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.5",
                        "3000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.9",
                    ],
                ),
                encoding="utf-8",
            )
            feature_path = Path(directory) / "features.csv"
            feature_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price,volume",
                        "1000000000,BTCUSDT.BINANCE,100,1",
                        "2000000000,BTCUSDT.BINANCE,101,10",
                        "3000000000,BTCUSDT.BINANCE,102,100",
                        "4000000000,BTCUSDT.BINANCE,103,100",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_volume_interaction_context(
                alpha_path,
                feature_path,
                horizons_seconds=[1],
                bucket_count=2,
            )

        self.assertEqual(context.instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(context.alpha_name, "orderbook_imbalance_depth10")
        self.assertEqual(context.horizons_seconds, [1])
        self.assertEqual(len(context.raw_bucket_summaries), 2)
        self.assertEqual(len(context.interaction_bucket_summaries), 2)
        self.assertEqual(context.joined_count, 3)
        self.assertLess(context.points[0].volume_zscore, 0)
        self.assertGreater(context.points[-1].volume_zscore, 0)
        self.assertGreater(context.points[-1].volume_intensity, 0)
        self.assertAlmostEqual(
            context.points[-1].interaction_value,
            context.points[-1].alpha_value * context.points[-1].volume_intensity,
        )

    def test_render_volume_interaction_report_html_contains_comparison_data(self):
        from reports.volume_interaction_report import build_volume_interaction_context
        from reports.volume_interaction_report import render_volume_interaction_report_html

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
            feature_path = Path(directory) / "features.csv"
            feature_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price,volume",
                        "1000000000,BTCUSDT.BINANCE,100,1",
                        "2000000000,BTCUSDT.BINANCE,101,10",
                        "3000000000,BTCUSDT.BINANCE,102,10",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_volume_interaction_context(
                alpha_path,
                feature_path,
                horizons_seconds=[1],
                bucket_count=2,
            )
            html = render_volume_interaction_report_html(context)

        self.assertIn("Volume Interaction Report", html)
        self.assertIn("rawBucketSummaries", html)
        self.assertIn("interactionBucketSummaries", html)
        self.assertIn("Plotly.newPlot", html)


if __name__ == "__main__":
    unittest.main()
