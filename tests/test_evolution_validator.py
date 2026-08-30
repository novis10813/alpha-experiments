import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class EvolutionValidatorTests(unittest.TestCase):
    def test_run_candidate_validation_uses_workspace_reference_and_rejects_tampering(self):
        from evolution.families import FAMILY_REGISTRY
        from evolution.run_context import validate_run_candidate

        family = FAMILY_REGISTRY["trend-flow-confirmation-v1"]
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            reference = run / "initial_program.py"
            reference.write_text(family.seed_program.read_text(encoding="utf-8"), encoding="utf-8")
            metadata = {
                "family_id": family.family_id,
                "seed_program_sha256": __import__("hashlib").sha256(reference.read_bytes()).hexdigest(),
            }
            (run / "run_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            candidate = run / "candidate.py"
            candidate.write_text(reference.read_text(encoding="utf-8"), encoding="utf-8")
            self.assertTrue(validate_run_candidate(run, candidate).valid)
            candidate.write_text(candidate.read_text(encoding="utf-8").replace(family.family_id, "pullback-exhaustion-v1"), encoding="utf-8")
            self.assertFalse(validate_run_candidate(run, candidate).valid)

    def test_empty_validation_pool_records_inconclusive_without_holdout_access(self):
        from evolution.families import FAMILY_REGISTRY
        from evolution.validator import promote_top_candidates

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "run"
            (run / "top_candidates").mkdir(parents=True)
            family = FAMILY_REGISTRY["trend-flow-confirmation-v1"]
            reference = run / "initial_program.py"
            reference.write_text(family.seed_program.read_text(encoding="utf-8"), encoding="utf-8")
            (run / "run_metadata.json").write_text(json.dumps({
                "family_id": family.family_id,
                "seed_program_sha256": __import__("hashlib").sha256(reference.read_bytes()).hexdigest(),
            }), encoding="utf-8")
            candidate = run / "top_candidates" / "candidate.py"
            candidate.write_text(reference.read_text(encoding="utf-8"), encoding="utf-8")
            (run / "top_candidates" / "index.json").write_text(json.dumps([{
                "candidate_id": "c1", "program_path": str(candidate),
                "metrics": {"combined_score": 1, "median_return": 1, "worst_return": 1,
                            "median_drawdown": 0, "median_profit_factor": 1, "closed_trades": 20,
                            "orders": 20, "exposure_ratio": 0, "active_folds": 5},
            }]), encoding="utf-8")
            rerank = {"candidates": [{"candidate_id": "c1", "deterministic": True,
                "executable": {"aggregate": {"net_sharpe": 1},
                "folds": [{"metrics": {"net_return": 1, "closed_positions": 1}} for _ in range(5)]}}]}
            sensitivity = {"candidate_id": "c1", "programs": {"executable_champion": {"labels": []}}}
            (run / "rerank.json").write_text(json.dumps(rerank), encoding="utf-8")
            (run / "sensitivity.json").write_text(json.dumps(sensitivity), encoding="utf-8")
            with patch("evolution.validator._load_split", return_value=([], [], [])) as load_split:
                with patch("evolution.validator.record_validation") as record:
                    with patch("evolution.backtest.run_candidate") as run_candidate:
                        with patch("evolution.validator.acquire_holdout_lock") as lock:
                            result = promote_top_candidates(
                                "BTCUSDT.BINANCE", root / "data", run,
                                family.family_id, "hypothesis", root / "governance", "run-1",
                            )
            self.assertEqual(result["status"], "inconclusive")
            self.assertTrue(result["validation_accessed"])
            self.assertFalse(result["holdout_accessed"])
            self.assertEqual(json.loads((run / "promotion-inconclusive.json").read_text())["status"], "inconclusive")
            load_split.assert_called_once()
            record.assert_called_once()
            run_candidate.assert_not_called()
            lock.assert_not_called()

    def test_candidate_path_falls_back_to_run_top_candidates(self):
        from evolution.validator import _candidate_path

        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            target = run / "top_candidates"
            target.mkdir()
            candidate = target / "01-c1.py"
            candidate.write_text("# candidate\n")
            path = _candidate_path(run, {"program_path": "/old/location/01-c1.py"})
            self.assertEqual(path, candidate)

    def test_disqualified_candidate_never_loads_validation(self):
        from evolution.validator import promote_top_candidates

        rerank = {"candidates": [{
            "candidate_id": "c1",
            "deterministic": True,
            "executable": {
                "aggregate": {"net_sharpe": -1.0},
                "folds": [
                    {"metrics": {"net_return": -0.01, "closed_positions": 4}}
                    for _ in range(5)
                ],
            },
        }]}
        sensitivity = {
            "candidate_id": "c1",
            "programs": {"executable_champion": {"labels": ["economically_rejected"]}},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "run"
            run.mkdir()
            (run / "rerank.json").write_text(json.dumps(rerank))
            (run / "sensitivity.json").write_text(json.dumps(sensitivity))
            with patch("evolution.validator._load_split", side_effect=AssertionError("split loaded")):
                result = promote_top_candidates(
                    "BTCUSDT.BINANCE", root / "data", run, "family-v1", "test hypothesis",
                    root / "governance", "run-1",
                )
        self.assertFalse(result["qualified"])
        self.assertFalse(result["validation_accessed"])
        self.assertFalse(result["holdout_accessed"])


if __name__ == "__main__":
    unittest.main()
