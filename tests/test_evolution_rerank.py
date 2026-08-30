import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class EvolutionRerankTests(unittest.TestCase):
    def test_load_candidates_uses_local_file_when_index_path_moved(self):
        from evolution.rerank import _load_candidates

        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            target = run / "top_candidates"
            target.mkdir()
            program = target / "01-c1.py"
            program.write_text("# candidate\n")
            (target / "index.json").write_text(json.dumps([{
                "rank": 1,
                "candidate_id": "c1",
                "program_path": "/old/location/01-c1.py",
                "metrics": {"combined_score": 1.0},
            }]))
            candidates = _load_candidates(run, 1)
        self.assertEqual(Path(candidates[0]["program_path"]).name, "01-c1.py")
        self.assertEqual(candidates[0]["fast_rank"], 1)

    def test_comparison_reports_execution_degradation(self):
        from evolution.rerank import _comparison

        fast = _payload(0.02, 2.0)
        executable = _payload(0.01, 1.0)
        comparison = _comparison(fast, executable)
        self.assertAlmostEqual(comparison["executable_minus_fast"]["net_return"], -0.01)
        self.assertAlmostEqual(comparison["executable_minus_fast"]["net_sharpe"], -1.0)
        self.assertEqual(comparison["fold_return_sign_retained"], 5)

    @patch("evolution.rerank._load_discovery_data")
    @patch("evolution.rerank._evaluate")
    def test_rerank_orders_by_executable_sharpe_and_checks_determinism(self, evaluate, load_data):
        from evolution.rerank import rerank_discovery_candidates

        load_data.return_value = []
        values = iter([
            _payload(0.02, 2.0), _payload(0.01, 1.0), _payload(0.01, 1.0),
            _payload(0.01, 1.0), _payload(0.03, 3.0), _payload(0.03, 3.0),
        ])
        evaluate.side_effect = lambda *args: next(values)
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            target = run / "top_candidates"
            target.mkdir()
            candidates = []
            for rank, candidate_id in enumerate(("a", "b"), start=1):
                path = target / f"0{rank}-{candidate_id}.py"
                path.write_text("# candidate\n")
                candidates.append({
                    "rank": rank,
                    "candidate_id": candidate_id,
                    "program_path": str(path),
                    "metrics": {},
                })
            (target / "index.json").write_text(json.dumps(candidates))
            output = run / "rerank.json"
            payload = rerank_discovery_candidates(
                "BTCUSDT.BINANCE", Path("fast"), Path("executable"), run, output,
                top_n=2, include_baselines=False,
            )
            written = output.read_text()
        self.assertEqual([item["candidate_id"] for item in payload["candidates"]], ["b", "a"])
        self.assertTrue(all(item["deterministic"] for item in payload["candidates"]))
        self.assertEqual(written, json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def test_similarity_signatures_and_summary_are_recorded_without_extra_evaluation(self):
        from evolution.rerank import rerank_discovery_candidates

        payloads = iter([
            _payload(0.02, 2.0), _payload(0.01, 1.0), _payload(0.01, 1.0),
            _payload(0.01, 1.0), _payload(0.03, 3.0), _payload(0.03, 3.0),
        ])
        with patch("evolution.rerank._load_discovery_data", return_value=[]), patch(
            "evolution.rerank._evaluate", side_effect=lambda *args: next(payloads),
        ) as evaluate:
            with tempfile.TemporaryDirectory() as directory:
                run = Path(directory)
                target = run / "top_candidates"
                target.mkdir()
                for rank, candidate_id in enumerate(("a", "b"), start=1):
                    path = target / f"0{rank}-{candidate_id}.py"
                    path.write_text("# candidate\n")
                    if candidate_id == "b":
                        path.write_text("# candidate\n# changed\n")
                    if rank == 1:
                        first = path
                    (target / "index.json").write_text(json.dumps([
                        {"rank": 1, "candidate_id": "a", "program_path": str(first), "metrics": {}},
                        {"rank": 2, "candidate_id": "b", "program_path": str(path), "metrics": {}},
                    ]))
                output = run / "rerank.json"
                result = rerank_discovery_candidates(
                    "BTCUSDT.BINANCE", Path("fast"), Path("executable"), run, output,
                    top_n=2, include_baselines=False,
                )
        self.assertEqual(evaluate.call_count, 6)
        summary = result["discovery_summary"]
        self.assertEqual(summary["evaluated_count"], 2)
        self.assertEqual(summary["unique_source_count"], 1)
        self.assertEqual(summary["unique_behavior_count"], 1)
        self.assertEqual(summary["duplicate_groups"], [["a", "b"]])

    def test_rank_stability_uses_candidate_ranks(self):
        from evolution.rerank import _rank_stability

        stability = _rank_stability([
            {"candidate_id": "a", "fast_rank": 1, "candidate_executable_rank": 2},
            {"candidate_id": "b", "fast_rank": 2, "candidate_executable_rank": 1},
            {"candidate_id": "c", "fast_rank": 3, "candidate_executable_rank": 3},
        ])
        self.assertEqual(stability["spearman"], 0.5)
        self.assertEqual(stability["top_3_overlap"], 3)

    def test_profile_loader_rejects_wrong_manifest_before_backtest(self):
        from evolution.rerank import _load_discovery_data

        manifest = SimpleNamespace(execution_profile="validation", execution_delay_seconds=1)
        with patch("evolution.rerank.discovery_split", return_value=(Path("split"), manifest)):
            with self.assertRaisesRegex(ValueError, "expected executable"):
                _load_discovery_data(Path("root"), "BTCUSDT.BINANCE", "executable")


def _payload(net_return, net_sharpe):
    aggregate = {
        "gross_return": net_return + 0.001,
        "fee_drag": 0.001,
        "net_return": net_return,
        "gross_sharpe": net_sharpe + 0.1,
        "net_sharpe": net_sharpe,
        "closed_positions": 10,
        "orders": 20,
        "turnover": 2.0,
        "exposure_ratio": 0.5,
        "average_holding_seconds": 60.0,
    }
    return {
        "aggregate": aggregate,
        "folds": [{"metrics": {"net_return": net_return}} for _ in range(5)],
    }


if __name__ == "__main__":
    unittest.main()
