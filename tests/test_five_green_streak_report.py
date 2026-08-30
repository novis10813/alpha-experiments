import tempfile
import unittest
from pathlib import Path


class FiveGreenStreakReportTests(unittest.TestCase):
    def test_build_context_detects_fifth_green_bar_and_forward_returns(self):
        from reports.five_green_streak_report import build_five_green_streak_context

        with tempfile.TemporaryDirectory() as directory:
            price_path = Path(directory) / "prices.csv"
            price_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price",
                        "10000000000,BTCUSDT.BINANCE,100",
                        "50000000000,BTCUSDT.BINANCE,101",
                        "70000000000,BTCUSDT.BINANCE,101",
                        "110000000000,BTCUSDT.BINANCE,102",
                        "130000000000,BTCUSDT.BINANCE,102",
                        "170000000000,BTCUSDT.BINANCE,103",
                        "190000000000,BTCUSDT.BINANCE,103",
                        "230000000000,BTCUSDT.BINANCE,104",
                        "250000000000,BTCUSDT.BINANCE,104",
                        "290000000000,BTCUSDT.BINANCE,105",
                        "310000000000,BTCUSDT.BINANCE,105",
                        "350000000000,BTCUSDT.BINANCE,106",
                        "370000000000,BTCUSDT.BINANCE,106",
                        "410000000000,BTCUSDT.BINANCE,107",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_five_green_streak_context(
                price_path,
                horizons_minutes=[1, 2],
                cooldown_minutes=[0, 5],
                cost_bps=[0, 10],
            )

        self.assertEqual(context.instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(context.bar_count, 7)
        self.assertEqual(context.raw_event_count, 3)
        self.assertEqual(context.cooldown_event_counts, {0: 3, 5: 1})
        self.assertEqual(context.events[0].ts_event, 300_000_000_000)
        self.assertEqual(context.events[0].trigger_index, 4)
        self.assertAlmostEqual(context.events[0].streak_return, 0.05)

        summary = _find_summary(context.summaries, horizon=1, cooldown=0, cost=0)
        self.assertEqual(summary.count, 2)
        self.assertAlmostEqual(summary.mean_gross_return, ((106 / 105) - 1 + (107 / 106) - 1) / 2)
        self.assertAlmostEqual(summary.mean_net_return, summary.mean_gross_return)
        self.assertEqual(summary.hit_rate, 1.0)

        cost_summary = _find_summary(context.summaries, horizon=1, cooldown=0, cost=10)
        self.assertAlmostEqual(cost_summary.mean_net_return, summary.mean_gross_return - 0.001)

        cooldown_summary = _find_summary(context.summaries, horizon=1, cooldown=5, cost=0)
        self.assertEqual(cooldown_summary.count, 1)

    def test_build_context_rejects_empty_horizons(self):
        from reports.five_green_streak_report import build_five_green_streak_context

        with tempfile.TemporaryDirectory() as directory:
            price_path = Path(directory) / "prices.csv"
            price_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price",
                        "10000000000,BTCUSDT.BINANCE,100",
                    ],
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "horizons_minutes must not be empty"):
                build_five_green_streak_context(price_path, horizons_minutes=[])

    def test_render_html_contains_summary_table_and_plot(self):
        from reports.five_green_streak_report import build_five_green_streak_context
        from reports.five_green_streak_report import render_five_green_streak_report_html

        with tempfile.TemporaryDirectory() as directory:
            price_path = Path(directory) / "prices.csv"
            price_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price",
                        "10000000000,BTCUSDT.BINANCE,100",
                        "50000000000,BTCUSDT.BINANCE,101",
                        "70000000000,BTCUSDT.BINANCE,101",
                        "110000000000,BTCUSDT.BINANCE,102",
                        "130000000000,BTCUSDT.BINANCE,102",
                        "170000000000,BTCUSDT.BINANCE,103",
                        "190000000000,BTCUSDT.BINANCE,103",
                        "230000000000,BTCUSDT.BINANCE,104",
                        "250000000000,BTCUSDT.BINANCE,104",
                        "290000000000,BTCUSDT.BINANCE,105",
                        "310000000000,BTCUSDT.BINANCE,105",
                        "350000000000,BTCUSDT.BINANCE,106",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_five_green_streak_context(price_path, horizons_minutes=[1])
            html = render_five_green_streak_report_html(context)

        self.assertIn("Five Green Streak Screen", html)
        self.assertIn("summaryRows", html)
        self.assertIn("Plotly.newPlot", html)
        self.assertIn("all_events", html)


def _find_summary(summaries, horizon: int, cooldown: int, cost: float):
    for summary in summaries:
        if (
            summary.horizon_minutes == horizon
            and summary.cooldown_minutes == cooldown
            and summary.cost_bps == cost
        ):
            return summary
    raise AssertionError("summary not found")


if __name__ == "__main__":
    unittest.main()
