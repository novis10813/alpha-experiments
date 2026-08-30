import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class EvolutionEvaluatorTests(unittest.TestCase):
    def test_invalid_candidate_has_fixed_low_score_and_bounded_artifact(self):
        from evolution.evaluator import evaluate

        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / "bad.py"
            program.write_text("this is not python(", encoding="utf-8")
            result = evaluate(str(program))
        self.assertEqual(result.metrics["combined_score"], -1_000_000)
        self.assertLess(result.get_total_artifact_size(), 3000)

    @patch("evolution.evaluator.run_sandbox")
    def test_sandbox_metrics_are_returned_with_complexity(self, sandbox):
        from evolution.evaluator import evaluate
        from evolution.sandbox import SandboxResult

        sandbox.return_value = SandboxResult(0, {"ok": True, "metrics": {
            "combined_score": 0.01, "median_return": 0.02, "worst_return": -0.01,
            "median_drawdown": 0.01, "median_profit_factor": 1.2, "closed_trades": 22,
            "orders": 44, "exposure_ratio": 0.3, "active_folds": 5,
        }}, None)
        with patch.dict(os.environ, {
            "EVOLUTION_DATASET_ROOT": "/dataset", "EVOLUTION_INSTRUMENT_ID": "BTCUSDT.BINANCE"
        }):
            result = evaluate("evolution/initial_program.py")
        self.assertEqual(result.metrics["combined_score"], 0.01)
        self.assertGreater(result.metrics["code_complexity"], 0)

    @patch("evolution.evaluator.run_sandbox")
    def test_mode_600_openevolve_candidate_is_staged_readable(self, sandbox):
        from evolution.evaluator import evaluate
        from evolution.sandbox import SandboxResult

        observed = {}

        def inspect_staged_program(program_path, *_args, **_kwargs):
            observed["mode"] = stat.S_IMODE(program_path.stat().st_mode)
            observed["code"] = program_path.read_text(encoding="utf-8")
            return SandboxResult(0, {"ok": True, "metrics": {
                "combined_score": 0.01, "median_return": 0.02, "worst_return": -0.01,
                "median_drawdown": 0.01, "median_profit_factor": 1.2, "closed_trades": 22,
                "orders": 44, "exposure_ratio": 0.3, "active_folds": 5,
            }}, None)

        sandbox.side_effect = inspect_staged_program
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / "candidate.py"
            reference = Path("evolution/initial_program.py").read_text(encoding="utf-8")
            program.write_text(reference, encoding="utf-8")
            program.chmod(0o600)
            with patch.dict(os.environ, {
                "EVOLUTION_DATASET_ROOT": "/dataset",
                "EVOLUTION_INSTRUMENT_ID": "BTCUSDT.BINANCE",
            }):
                evaluate(str(program))

        self.assertEqual(observed["mode"], 0o444)
        self.assertEqual(observed["code"], reference)


if __name__ == "__main__":
    unittest.main()
