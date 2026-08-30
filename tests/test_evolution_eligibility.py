import json
import tempfile
import unittest
from pathlib import Path


class EvolutionEligibilityTests(unittest.TestCase):
    def test_policy_reports_activity_reasons(self):
        from evolution.eligibility import RejectionReason
        from evolution.eligibility import evaluate_eligibility
        from evolution.metrics import FoldMetrics

        result = evaluate_eligibility((FoldMetrics(0.1, 0.01, 1, 3, 6, 0.2, (0.01, 0.02)),) * 3)
        self.assertFalse(result.eligible)
        self.assertIn(RejectionReason.INSUFFICIENT_TRADES, result.reasons)
        self.assertIn(RejectionReason.INSUFFICIENT_ACTIVE_FOLDS, result.reasons)

    def test_checkpoint_audit_does_not_invent_missing_reasons(self):
        from evolution.eligibility import audit_checkpoint_eligibility

        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory)
            programs = checkpoint / "programs"
            programs.mkdir()
            (programs / "a.json").write_text(json.dumps({
                "metrics": {"combined_score": 1, "closed_trades": 15, "active_folds": 5},
            }))
            (programs / "b.json").write_text(json.dumps({
                "metrics": {"combined_score": -1_000_000},
            }))
            result = audit_checkpoint_eligibility(checkpoint)
        self.assertEqual(result["program_count"], 2)
        self.assertEqual(result["programs_with_activity_metrics"], 1)
        self.assertEqual(result["fixed_score_rejections"], 1)
        self.assertEqual(result["thresholds"][0]["eligible_candidates"], 1)
        self.assertEqual(result["thresholds"][-1]["eligible_candidates"], 0)
        self.assertIn("do not preserve", result["historical_reason_limit"])


if __name__ == "__main__":
    unittest.main()
