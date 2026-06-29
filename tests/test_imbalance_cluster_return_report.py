import tempfile
import unittest
from pathlib import Path


class ImbalanceClusterReturnReportTests(unittest.TestCase):
    def test_build_context_finds_cluster_and_forward_return(self):
        from reports.imbalance_cluster_return_report import build_imbalance_cluster_return_context

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "aligned.csv"
            _write_rows(
                source,
                closes=[100, 101, 102, 103, 105, 106],
                imbalances=[0.96, 0.10, 0.97, 0.20, 0.10, 0.10],
            )

            context = build_imbalance_cluster_return_context(
                source,
                lookback_minutes=3,
                min_high_count=2,
                threshold=0.95,
                horizon_minutes=2,
                cooldown_minutes=0,
            )

        self.assertEqual(context.row_count, 6)
        self.assertEqual(len(context.raw_events), 1)
        event = context.raw_events[0]
        self.assertEqual(event.timestamp, "2026-06-17T00:03:00Z")
        self.assertEqual(event.high_count, 2)
        self.assertAlmostEqual(event.forward_return, (105 / 102) - 1)

        raw_summary = next(summary for summary in context.summaries if summary.group == "raw_cluster_events")
        self.assertEqual(raw_summary.count, 1)
        self.assertAlmostEqual(raw_summary.mean_forward_return, (105 / 102) - 1)

    def test_cooldown_deoverlaps_consecutive_cluster_events(self):
        from reports.imbalance_cluster_return_report import build_imbalance_cluster_return_context

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "aligned.csv"
            _write_rows(
                source,
                closes=[100, 101, 102, 103, 104, 105, 106],
                imbalances=[0.96, 0.97, 0.98, 0.99, 0.10, 0.10, 0.10],
            )

            context = build_imbalance_cluster_return_context(
                source,
                lookback_minutes=3,
                min_high_count=2,
                threshold=0.95,
                horizon_minutes=1,
                cooldown_minutes=2,
            )

        self.assertEqual(len(context.raw_events), 3)
        self.assertEqual([event.timestamp for event in context.cooldown_events], ["2026-06-17T00:03:00Z", "2026-06-17T00:05:00Z"])

    def test_missing_kbar_gap_does_not_allow_windows_to_cross_segments(self):
        from reports.imbalance_cluster_return_report import build_imbalance_cluster_return_context

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "aligned.csv"
            _write_rows(
                source,
                closes=[100, 101, 102, 103, 104, 105, 106],
                imbalances=[0.96, 0.10, 0.10, 0.98, 0.99, 0.10, 0.10],
                skip_after_index=2,
            )

            context = build_imbalance_cluster_return_context(
                source,
                lookback_minutes=3,
                min_high_count=2,
                threshold=0.95,
                horizon_minutes=1,
                cooldown_minutes=0,
            )

        self.assertEqual(len(context.raw_events), 1)
        self.assertEqual(context.raw_events[0].timestamp, "2026-06-17T00:07:00Z")

    def test_render_html_contains_summary_payload(self):
        from reports.imbalance_cluster_return_report import build_imbalance_cluster_return_context
        from reports.imbalance_cluster_return_report import render_imbalance_cluster_return_report_html

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "aligned.csv"
            _write_rows(
                source,
                closes=[100, 101, 102, 103, 105, 106],
                imbalances=[0.96, 0.10, 0.97, 0.20, 0.10, 0.10],
            )
            context = build_imbalance_cluster_return_context(
                source,
                lookback_minutes=3,
                min_high_count=2,
                horizon_minutes=2,
                cooldown_minutes=0,
            )
            html = render_imbalance_cluster_return_report_html(context)

        self.assertIn("Imbalance Cluster Forward Return", html)
        self.assertIn("raw_cluster_events", html)
        self.assertIn("Plotly.newPlot", html)


def _write_rows(
    source: Path,
    closes: list[float],
    imbalances: list[float],
    skip_after_index: int | None = None,
) -> None:
    header = (
        "start_time,end_time,ts_event,timestamp,instrument_id,open,high,low,close,volume,trade_count,"
        "trade_id_start,trade_id_end,expected_trade_count,trade_id_gap_count,expected_coverage_count,"
        "orderbook_coverage_count,orderbook_sample_count,orderbook_imbalance_mean,orderbook_imbalance_last,"
        "orderbook_imbalance_min,orderbook_imbalance_max,imbalance_basis,imbalance_value,"
        "imbalance_x_volume,imbalance_x_trade_count"
    )
    base = 1_781_654_400_000_000_000
    interval = 60_000_000_000
    lines = [header]
    for index, (close, imbalance) in enumerate(zip(closes, imbalances, strict=True)):
        gap_offset = interval if skip_after_index is not None and index > skip_after_index else 0
        start = base + index * interval + gap_offset
        end = start + interval
        minute = ((end - base) // interval)
        timestamp = f"2026-06-17T00:{minute:02d}:00Z"
        lines.append(
            f"{start},{end},{end},{timestamp},BTCUSDT.BINANCE,{close},{close},{close},{close},1.0,10,"
            f"{index * 10},{index * 10 + 9},10,0,60,60,60,{imbalance},{imbalance},{imbalance},{imbalance},"
            f"mean,{imbalance},{imbalance},{imbalance * 10}",
        )
    source.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
