import csv
import json
import tempfile
import unittest
from pathlib import Path


class EvolutionReportTests(unittest.TestCase):
    def test_rejected_report_and_canonical_alpha_columns(self):
        from evolution.metrics import AggregateMetrics
        from evolution.metrics import FoldMetrics
        from evolution.report import write_alpha_signal
        from evolution.report import write_research_report
        from evolution.selection import CandidateResult

        discovery = AggregateMetrics(0.1, 0.1, 0.01, 0.02, 1.2, 20, 40, 0.3, 5)
        candidate = CandidateResult("c1", discovery, FoldMetrics(-0.01, 0.03, 0.5, 3, 6, 0.2))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metrics, report = write_research_report(candidate, False, {"sma": -0.02}, root)
            payload = json.loads(metrics.read_text())
            self.assertEqual(payload["status"], "rejected")
            self.assertIn("baseline_differences", report.read_text())
            alpha = root / "alpha.csv"
            write_alpha_signal([(1, "BTCUSDT.BINANCE", "candidate", 1.0)], alpha)
            with alpha.open() as stream:
                self.assertEqual(next(csv.reader(stream)), ["ts_event", "instrument_id", "alpha_name", "value"])


if __name__ == "__main__":
    unittest.main()

