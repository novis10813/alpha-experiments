import tempfile
import unittest
from pathlib import Path


class ObiMaSpreadReportTests(unittest.TestCase):
    def test_build_context_computes_spread_groups_and_forward_returns(self):
        from reports.obi_ma_spread_report import build_obi_ma_spread_context

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "kbar_obi.csv"
            source.write_text(_rows_csv(), encoding="utf-8")

            context = build_obi_ma_spread_context(
                source,
                short_window=2,
                long_window=3,
                horizons_minutes=[1],
                cooldown_minutes=[0, 2],
                cost_bps=[0, 10],
            )

        self.assertEqual(context.instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(context.bar_count, 6)
        self.assertEqual(context.signal_count, 4)
        self.assertEqual(context.event_counts["spread_positive"], 3)
        self.assertEqual(context.event_counts["spread_positive_short_positive"], 1)
        self.assertEqual(context.cooldown_event_counts["spread_positive"][0], 3)
        self.assertEqual(context.cooldown_event_counts["spread_positive"][2], 2)

        first_signal = context.signals[0]
        self.assertEqual(first_signal.ts_event, 180_000_000_000)
        self.assertAlmostEqual(first_signal.short_mean, -0.2)
        self.assertAlmostEqual(first_signal.long_mean, -0.3)
        self.assertAlmostEqual(first_signal.spread, 0.1)

        positive_summary = _find_summary(
            context.summaries,
            group="spread_positive",
            horizon=1,
            cooldown=0,
            cost=0,
        )
        self.assertEqual(positive_summary.count, 3)
        expected_returns = [
            (104 / 103) - 1,
            (105 / 104) - 1,
            (106 / 105) - 1,
        ]
        self.assertAlmostEqual(
            positive_summary.mean_gross_return,
            sum(expected_returns) / len(expected_returns),
        )

        cost_summary = _find_summary(
            context.summaries,
            group="spread_positive",
            horizon=1,
            cooldown=0,
            cost=10,
        )
        self.assertAlmostEqual(
            cost_summary.mean_net_return,
            positive_summary.mean_gross_return - 0.001,
        )

        strict_summary = _find_summary(
            context.summaries,
            group="spread_positive_short_positive",
            horizon=1,
            cooldown=0,
            cost=0,
        )
        self.assertEqual(strict_summary.count, 1)

    def test_build_context_rejects_short_window_not_less_than_long_window(self):
        from reports.obi_ma_spread_report import build_obi_ma_spread_context

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "kbar_obi.csv"
            source.write_text(_rows_csv(), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "short_window must be less than long_window"):
                build_obi_ma_spread_context(source, short_window=3, long_window=3)

    def test_render_html_contains_summary_payload(self):
        from reports.obi_ma_spread_report import build_obi_ma_spread_context
        from reports.obi_ma_spread_report import render_obi_ma_spread_report_html

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "kbar_obi.csv"
            source.write_text(_rows_csv(), encoding="utf-8")

            context = build_obi_ma_spread_context(
                source,
                short_window=2,
                long_window=3,
                horizons_minutes=[1],
            )
            html = render_obi_ma_spread_report_html(context)

        self.assertIn("OBI MA Spread Screen", html)
        self.assertIn("summaryRows", html)
        self.assertIn("spread_positive_short_positive", html)
        self.assertIn("Plotly.newPlot", html)


def _rows_csv() -> str:
    lines = [
        "start_time,end_time,ts_event,timestamp,instrument_id,open,high,low,close,orderbook_imbalance_mean",
    ]
    values = [
        (0, 60_000_000_000, 100, 101, -0.5),
        (60_000_000_000, 120_000_000_000, 101, 102, -0.3),
        (120_000_000_000, 180_000_000_000, 102, 103, -0.1),
        (180_000_000_000, 240_000_000_000, 103, 104, 0.1),
        (240_000_000_000, 300_000_000_000, 104, 105, 0.2),
        (300_000_000_000, 360_000_000_000, 105, 106, -0.2),
    ]
    for start, end, open_price, close_price, imbalance in values:
        lines.append(
            f"{start},{end},{end},2026-06-17T00:00:00Z,BTCUSDT.BINANCE,"
            f"{open_price},{close_price},{open_price},{close_price},{imbalance}",
        )
    return "\n".join(lines)


def _find_summary(summaries, group: str, horizon: int, cooldown: int, cost: float):
    for summary in summaries:
        if (
            summary.group == group
            and summary.horizon_minutes == horizon
            and summary.cooldown_minutes == cooldown
            and summary.cost_bps == cost
        ):
            return summary
    raise AssertionError("summary not found")


if __name__ == "__main__":
    unittest.main()
