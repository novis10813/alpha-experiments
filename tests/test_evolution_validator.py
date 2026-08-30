import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class EvolutionValidatorTests(unittest.TestCase):
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
