import asyncio
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version as package_version
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

from openevolve.config import LLMModelConfig
from openevolve.llm.ensemble import LLMEnsemble

from experiments.open_evolve.openevolve_backend import (
    OpenEvolveSearch, SearchSettings, make_ensemble, search_feedback,
)
from experiments.open_evolve.cli import SYSTEM_PROMPT, validate_config
from experiments.open_evolve.search import finalize
from test_open_evolve_pipeline import FLAT, RULE, LIMITS, fixture
from test_open_evolve_search import cell, score


class ScriptedLLM:
    def __init__(self, responses):
        self.model = "offline-scripted"
        self.responses = iter(responses)
        self.prompts = []

    async def generate_with_context(self, system_message, messages, **kwargs):
        self.prompts.append((system_message, messages))
        return next(self.responses)


def ensemble_for(client):
    return LLMEnsemble([LLMModelConfig(name=client.model, init_client=lambda cfg: client)])


class OpenEvolveTests(unittest.TestCase):
    def make_search(self, directory, evaluate=lambda p: [cell()], **kwargs):
        return OpenEvolveSearch(output=Path(directory), contract={"holdout": "SECRET_HOLDOUT_WINDOW"},
                                limits=LIMITS, score=score(), evaluate=evaluate,
                                settings=SearchSettings(migration_interval=1),
                                system_prompt=SYSTEM_PROMPT, **kwargs)

    def test_real_database_sampling_prompt_lineage_cache_and_holdout(self):
        calls = []
        def evaluate(policy):
            calls.append(policy.source_hash)
            return [cell()]
        client = ScriptedLLM(["```python\n" + RULE + "```", RULE.strip(), "import os", FLAT])
        with tempfile.TemporaryDirectory() as directory:
            search = self.make_search(directory, evaluate)
            selected = search.run([FLAT], budget=5, ensemble=ensemble_for(client))
            self.assertEqual(len(calls), 3)  # Raw source hashes distinguish final-newline differences.
            self.assertEqual(selected["status"], "selected")
            self.assertEqual(len(search.records), 5)
            self.assertEqual(search.records[3]["ranking"]["status"], "invalid_candidate")
            self.assertNotIn("attempt-00003", search.database.programs)
            self.assertTrue(search.records[2]["cached"])
            self.assertTrue(all(r["parent_hash"] for r in search.records[1:]))
            self.assertTrue(all(r["request"]["parent_id"] for r in search.records[1:]))
            self.assertNotIn("SECRET_HOLDOUT_WINDOW", json.dumps(client.prompts))
            self.assertIn("evaluation", json.dumps(client.prompts))
            self.assertEqual(search.database.config.feature_dimensions, ["trade_count", "turnover"])
            self.assertTrue((Path(directory) / "openevolve-database/metadata.json").exists())
            self.assertFalse((Path(directory) / "holdout-started.json").exists())
            calls = []
            def holdout(policy, contract):
                calls.append(policy.source_hash)
                return [cell()]
            finalize(Path(directory), expected_contract_hash=selected["contract_hash"], evaluate_holdout=holdout)
            with self.assertRaises(FileExistsError):
                finalize(Path(directory), expected_contract_hash=selected["contract_hash"], evaluate_holdout=holdout)
            self.assertEqual(len(calls), 1)

    def test_failed_candidates_have_feedback_but_no_final_selection(self):
        failed = cell()
        failed["metrics"]["trade_count"] = 0
        failed["metrics"]["sharpe"] = None
        client = ScriptedLLM([RULE])
        with tempfile.TemporaryDirectory() as directory:
            search = self.make_search(directory, lambda p: [failed])
            selection = search.run([FLAT], budget=2, ensemble=ensemble_for(client))
            self.assertEqual(selection["status"], "no_eligible_candidate")
            self.assertTrue(search.database.programs)
            self.assertIn("normalized_violations", json.dumps(client.prompts))
            self.assertIn("trade_count", json.dumps(client.prompts))
            with self.assertRaises(ValueError):
                finalize(Path(directory), expected_contract_hash=selection["contract_hash"],
                         evaluate_holdout=lambda *args: self.fail("holdout accessed"))
            self.assertFalse((Path(directory) / "holdout-started.json").exists())

    def test_selection_does_not_trust_upstream_best(self):
        with tempfile.TemporaryDirectory() as directory:
            search = self.make_search(directory)
            with patch.object(search.database, "get_best_program", side_effect=AssertionError("must not use upstream best")):
                selection = search.run([FLAT], budget=1)
            self.assertEqual(selection["status"], "selected")

    def test_infrastructure_and_incomplete_results_abort(self):
        for result in ([{"status": "infrastructure_error"}], [], [cell(), cell()]):
            with self.subTest(result=result), tempfile.TemporaryDirectory() as directory:
                search = self.make_search(directory, lambda p: result,
                                          expected_cells={("evolution", "base")})
                with self.assertRaises(RuntimeError):
                    search.run([FLAT], budget=1)
                self.assertTrue((Path(directory) / "search-error.json").exists())
                self.assertFalse((Path(directory) / "selection.json").exists())

    def test_all_invalid_seeds_abort_before_model(self):
        client = ScriptedLLM([FLAT])
        with tempfile.TemporaryDirectory() as directory:
            search = self.make_search(directory, lambda p: self.fail("invalid executed"))
            with self.assertRaises(ValueError):
                search.run(["import os"], budget=2, ensemble=ensemble_for(client))
            self.assertEqual(client.prompts, [])
            self.assertFalse((Path(directory) / "selection.json").exists())

    def test_search_score_bands_and_distance(self):
        def record(sharpe, status, fitness=None):
            c = cell()
            c["metrics"]["sharpe"] = sharpe
            return {"source": FLAT, "cells": [c],
                    "ranking": {"status": status, "fitness": fitness}}
        near, _ = search_feedback(record(-11, "constraint_failed"), score())
        far, _ = search_feedback(record(-100, "constraint_failed"), score())
        eligible, _ = search_feedback(record(1, "valid", -1000), score())
        self.assertGreater(near["combined_score"], far["combined_score"])
        self.assertGreater(eligible["combined_score"], near["combined_score"])
        self.assertGreaterEqual(eligible["combined_score"], 2)
        json.dumps(far, allow_nan=False)

    def test_config_validation_and_contract_settings(self):
        config = json.loads(Path("experiments/open_evolve/example.config.json").read_text())
        config["search"] = {"backend": "openevolve", "num_islands": 2, "population_size": 8}
        validate_config(config)
        config["search"]["population_size"] = 1
        with self.assertRaises(ValueError):
            validate_config(config)
        config["search"] = {"backend": "legacy"}
        validate_config(config)
        with tempfile.TemporaryDirectory() as directory:
            search = self.make_search(directory)
            self.assertEqual(search.contract["search"]["version"], package_version("openevolve"))
            self.assertEqual(search.contract["search"]["settings"]["num_islands"], 2)

    def test_full_openevolve_demo_with_synthetic_holdout(self):
        from experiments.open_evolve.demo import run_demo
        with tempfile.TemporaryDirectory() as directory:
            selection = run_demo(Path(directory), backend="openevolve")
            self.assertEqual(selection["status"], "selected")
            result = json.loads((Path(directory) / "holdout-result.json").read_text())
            self.assertEqual(len(result["cells"]), 2)
            self.assertTrue(all(c["status"] == "valid" for c in result["cells"]))

    def test_real_nautilus_with_openevolve(self):
        from experiments.open_evolve.backtest import run_backtest
        instrument, trades, depths, features, execution, fold, scenario, metric = fixture()
        def evaluate(policy):
            return [run_backtest(instrument, trades, depths, policy, features, execution, fold, s, metric)
                    for s in (scenario, replace(scenario, name="stress", order_ns=10_000_000))]
        client = ScriptedLLM([RULE])
        with tempfile.TemporaryDirectory() as directory:
            search = self.make_search(directory, evaluate,
                                      expected_cells={(fold.name, "base"), (fold.name, "stress")})
            search.run([FLAT], budget=2, ensemble=ensemble_for(client))
            self.assertEqual(len(search.records), 2)
            for c in search.records[1]["cells"]:
                self.assertEqual(c["status"], "valid")
                self.assertGreater(c["metrics"]["fees"], 0)
                self.assertAlmostEqual(c["metrics"]["gross_pnl"] - c["metrics"]["fees"], c["metrics"]["net_pnl"])

    def test_cli_defaults_to_openevolve_and_loads_only_evolution(self):
        from experiments.open_evolve.cli import main
        instrument = fixture()[0]
        config = json.loads(Path("experiments/open_evolve/example.config.json").read_text())
        config.pop("search", None)
        config["budget"] = 1
        loaded_names = []
        def load(catalog, iid, fold, max_events):
            loaded_names.append(fold.name)
            return [], [], "fake-data-hash"
        cells = []
        for f in config["folds"]:
            for s in config["scenarios"]:
                c = cell()
                c.update(fold=f["name"], scenario=s["name"])
                c["metrics"]["trade_count"] = 30
                cells.append(c)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "config.json").write_text(json.dumps(config))
            with patch("experiments.open_evolve.cli.make_catalog"), \
                 patch("experiments.open_evolve.cli.resolve_instrument", return_value=(instrument, "test")), \
                 patch("experiments.open_evolve.cli.load_fold", side_effect=load), \
                 patch("experiments.open_evolve.cli.evaluator", return_value=lambda policy: cells), \
                 patch("builtins.print"):
                main(["evolve", str(path / "config.json"), str(path / "run")])
            manifest = json.loads((path / "run/contract.json").read_text())
            self.assertEqual(manifest["contract"]["search"]["backend"], "openevolve")
            prompt = manifest["contract"]["system_prompt"]
            self.assertIn("taker_fee_bps_per_side", prompt)
            self.assertNotIn(str(config["holdout"]["warmup_start"]), prompt)
            self.assertEqual(loaded_names, [f["name"] for f in config["folds"]])
            self.assertFalse((path / "run/holdout-started.json").exists())

    def test_proposer_failure_preserves_seed_and_does_not_select(self):
        class BrokenModel:
            async def generate_with_context(self, **kwargs):
                raise TimeoutError("private endpoint details")
        with tempfile.TemporaryDirectory() as directory:
            search = self.make_search(directory)
            with self.assertRaises(TimeoutError):
                search.run([FLAT], budget=2, ensemble=BrokenModel())
            error = (Path(directory) / "search-error.json").read_text()
            self.assertIn("TimeoutError", error)
            self.assertNotIn("private endpoint", error)
            self.assertTrue((Path(directory) / "candidate-00000.json").exists())
            self.assertFalse((Path(directory) / "selection.json").exists())

    def test_http_client_sends_thinking_off_and_rejects_empty_or_truncated(self):
        requests = []
        responses = [("stop", FLAT), ("stop", ""), ("length", FLAT)]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                reason, content = responses.pop(0)
                body = json.dumps({"id": "test", "object": "chat.completion", "created": 0,
                                   "model": "qwen3.8-27b", "choices": [{"index": 0, "finish_reason": reason,
                                   "message": {"role": "assistant", "content": content}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict("os.environ", {
                "EVOLVE_MODEL_ENDPOINT": f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                "EVOLVE_MODEL_API_KEY": "local-test-key",
            }):
                ensemble = make_ensemble({"model": "qwen3.8-27b", "temperature": 0.5, "max_tokens": 100}, SearchSettings())
                async def request():
                    return await ensemble.generate_with_context(system_message="test", messages=[])
                try:
                    self.assertEqual(asyncio.run(request()), FLAT)
                    for _ in range(2):
                        with self.assertRaises(ValueError):
                            asyncio.run(request())
                finally:
                    ensemble.models[0].client.close()
            self.assertEqual(len(requests), 3)
            self.assertTrue(all(r["chat_template_kwargs"] == {"enable_thinking": False} for r in requests))
            self.assertNotIn("local-test-key", json.dumps(requests))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
