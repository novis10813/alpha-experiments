from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest

from experiments.open_evolve.search import EvolutionSearch, finalize
from experiments.open_evolve.evaluation import ScoreConfig
from experiments.open_evolve.policy import PolicyLimits
from experiments.open_evolve.cli import validate_config, evaluator
from test_open_evolve_pipeline import fixture, FLAT, RULE, LIMITS


def cell():
    return {"status": "valid", "fold": "evolution", "scenario": "base",
            "metrics": {"trade_count": 2, "max_drawdown": 0.01, "turnover": 1,
                        "sharpe": 1, "sortino": 2, "profit_factor": 2},
            "markout": {h: {"coverage": 1, "weighted_mean": 1} for h in ("100ms", "1s")}}


def score():
    return ScoreConfig(1, 0.2, 10, -10, 0.5,
                       {"median_sharpe": 1, "complexity": -0.01},
                       {"median_sharpe": 1, "complexity": 100}, 10)


class SearchTests(unittest.TestCase):
    def test_lineage_duplicate_cache_and_one_shot_holdout(self):
        calls, requests, holdout = [], [], []
        def evaluate(policy):
            calls.append(policy.source_hash)
            return [cell()]
        def propose(request):
            requests.append(request)
            return FLAT
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            search = EvolutionSearch(output=output, contract={"data": "evolution-only"},
                                     limits=LIMITS, score=score(), evaluate=evaluate)
            selection = search.run([FLAT], budget=3, propose=propose)
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(requests), 2)
            self.assertEqual(holdout, [])
            def evaluate_holdout(policy, contract):
                holdout.append(policy.source_hash)
                return [cell()]
            result = finalize(output, expected_contract_hash=selection["contract_hash"],
                              evaluate_holdout=evaluate_holdout)
            self.assertEqual(len(holdout), 1)
            self.assertEqual(result["candidate_hash"], selection["candidate_hash"])
            with self.assertRaises(FileExistsError):
                finalize(output, expected_contract_hash=selection["contract_hash"], evaluate_holdout=evaluate_holdout)
            self.assertEqual(len(holdout), 1)

    def test_invalid_source_is_recorded_without_evaluator_call(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            search = EvolutionSearch(output=output, contract={}, limits=LIMITS,
                                     score=score(), evaluate=lambda p: self.fail("invalid source reached runner"))
            result = search.run(["import os"], budget=1)
            self.assertEqual(result["status"], "no_eligible_candidate")
            record = json.loads((output / "candidate-00000.json").read_text())
            self.assertEqual(record["ranking"]["status"], "invalid_candidate")
            with self.assertRaises(ValueError):
                finalize(output, expected_contract_hash=result["contract_hash"],
                         evaluate_holdout=lambda *a: self.fail("holdout accessed"))

    def test_frozen_source_tampering_fails_before_holdout(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            search = EvolutionSearch(output=output, contract={}, limits=LIMITS,
                                     score=score(), evaluate=lambda p: [cell()])
            selection = search.run([FLAT], budget=1)
            selection["source"] = RULE
            (output / "selection.json").write_text(json.dumps(selection))
            with self.assertRaises(ValueError):
                finalize(output, expected_contract_hash=search.identity,
                         evaluate_holdout=lambda *a: self.fail("holdout accessed"))
            self.assertFalse((output / "holdout-started.json").exists())

    def test_infrastructure_error_stops_instead_of_omitting_fold(self):
        with tempfile.TemporaryDirectory() as directory:
            search = EvolutionSearch(output=Path(directory), contract={}, limits=LIMITS,
                                     score=score(), evaluate=lambda p: [{"status": "infrastructure_error"}])
            with self.assertRaises(RuntimeError):
                search.run([FLAT], budget=1)
            self.assertFalse((Path(directory) / "selection.json").exists())

    def test_example_config_and_overlap_rejection(self):
        config = json.loads(Path("experiments/open_evolve/example.config.json").read_text())
        validate_config(config)
        config["holdout"]["warmup_start"] = config["folds"][-1]["end"]
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_synthetic_end_to_end_evolution_and_holdout(self):
        from experiments.open_evolve.demo import run_demo
        with tempfile.TemporaryDirectory() as directory:
            selection = run_demo(Path(directory))
            self.assertEqual(selection["status"], "selected")
            result = json.loads((Path(directory) / "holdout-result.json").read_text())
            self.assertEqual(len(result["cells"]), 2)
            self.assertTrue(all(c["status"] == "valid" for c in result["cells"]))
            first = json.loads((Path(directory) / "candidate-00000.json").read_text())
            self.assertEqual(len(first["cells"]), 4)

    def test_backtest_emits_configured_markout_horizons(self):
        from dataclasses import replace
        from experiments.open_evolve.backtest import run_backtest
        from experiments.open_evolve.evaluation import MetricConfig
        from experiments.open_evolve.policy import Policy
        instrument, trades, depths, features, execution, fold, scenario, metric = fixture()
        metric3 = replace(metric, markout_horizons={"1s": 1_000_000_000, "5s": 5_000_000_000})
        result = run_backtest(instrument, trades, depths, Policy(RULE, LIMITS), features,
                              execution, fold, scenario, metric3)
        self.assertEqual(result["status"], "valid", result)
        self.assertEqual(set(result["markout"]), {"1s", "5s"})
        self.assertEqual(set(result["markout_groups"]["entry"]), {"1s", "5s"})
        with self.assertRaises(ValueError):
            MetricConfig(1, 0, 0, 100, 1, markout_horizons={})
        with self.assertRaises(ValueError):
            MetricConfig(1, 0, 0, 100, 1, markout_horizons={"5s": -1})

    def test_score_gate_and_vector_cover_all_configured_horizons(self):
        from dataclasses import replace
        from experiments.open_evolve.evaluation import rank_results
        c = cell()
        c["markout"]["5s"] = {"coverage": 1, "weighted_mean": 0.5}
        s3 = replace(score(), markout_horizons=("100ms", "1s", "5s"))
        ranking = rank_results([c], 10, s3)
        self.assertEqual(ranking["status"], "valid")
        self.assertEqual(ranking["vector"]["markout_5s"], 0.5)
        low = cell()
        low["markout"]["5s"] = {"coverage": 0.1, "weighted_mean": 0.5}
        self.assertIn("cell 0: coverage", rank_results([low], 10, s3)["violations"])

    def test_validate_config_max_holding_bounded_by_fold(self):
        config = json.loads(Path("experiments/open_evolve/example.config.json").read_text())
        fold_ns = config["folds"][0]["end"] - config["folds"][0]["start"]
        config["execution"]["max_holding_ns"] = fold_ns + 1
        with self.assertRaises(ValueError):
            validate_config(config)
        config["execution"]["max_holding_ns"] = fold_ns
        validate_config(config)

    def test_validate_config_horizon_cross_check(self):
        config = json.loads(Path("experiments/open_evolve/example.config.json").read_text())
        config["score"]["weights"]["markout_5s"] = 0.1
        config["score"]["scales"]["markout_5s"] = 1.0
        config["score"]["markout_horizons"] = ["100ms", "1s", "5s"]
        config["metrics"]["markout_horizons"] = {"100ms": 100000000, "1s": 1000000000}
        with self.assertRaises(ValueError):
            validate_config(config)
        config["metrics"]["markout_horizons"]["5s"] = 5000000000
        validate_config(config)

    def test_cached_and_streaming_nautilus_results_match(self):
        from experiments.open_evolve.backtest import run_backtest
        from experiments.open_evolve.policy import Policy
        instrument, trades, depths, features, execution, fold, scenario, metric = fixture()
        config = {"features": {k: v for k, v in asdict(features).items() if k != "instrument_id"},
                  "execution": asdict(execution), "metrics": asdict(metric), "scenarios": [asdict(scenario)]}
        policy = Policy(RULE, LIMITS)
        cached = evaluator(config, instrument, [(fold, trades, depths, "synthetic")])(policy)[0]
        streamed = run_backtest(instrument, trades, depths, policy, features, execution, fold, scenario, metric)
        self.assertEqual(cached, streamed)


if __name__ == "__main__":
    unittest.main()
