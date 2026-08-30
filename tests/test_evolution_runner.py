import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


class EvolutionRunnerTests(unittest.TestCase):
    def test_base_config_matches_openrouter_and_map_elites_plan(self):
        from evolution.config import load_base_config

        config = load_base_config()
        self.assertEqual(config["llm"]["api_base"], "https://openrouter.ai/api/v1")
        self.assertEqual(
            [model["name"] for model in config["llm"]["models"]],
            ["nvidia/nemotron-3-super-120b-a12b:free", "nvidia/nemotron-3-ultra-550b-a55b:free"],
        )
        self.assertEqual([model["weight"] for model in config["llm"]["models"]], [0.8, 0.2])
        self.assertEqual(config["llm"]["timeout"], 240)
        self.assertEqual(config["llm"]["retries"], 1)
        template_dir = Path(config["prompt"]["template_dir"])
        self.assertIn("Modify only code strictly between", (template_dir / "system_message.txt").read_text())
        self.assertIn("inside the EVOLVE block", (template_dir / "diff_user.txt").read_text())
        self.assertEqual(config["database"]["num_islands"], 3)
        self.assertEqual(config["database"]["population_size"], 200)
        self.assertEqual(config["database"]["archive_size"], 1)
        self.assertEqual(config["database"]["exploration_ratio"], 0.0)
        self.assertEqual(config["database"]["exploitation_ratio"], 1.0)
        self.assertEqual(config["evaluator"]["parallel_evaluations"], 2)
        self.assertFalse(config["evaluator"]["use_llm_feedback"])

    def test_export_top_candidates_uses_archive_and_score(self):
        from evolution.runner import export_top_candidates

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint = root / "checkpoint_30"
            (checkpoint / "programs").mkdir(parents=True)
            (checkpoint / "metadata.json").write_text(json.dumps({"archive": ["a"]}))
            for candidate_id, score in (("a", 0.1), ("b", 0.2)):
                (checkpoint / "programs" / f"{candidate_id}.json").write_text(json.dumps({
                    "id": candidate_id, "code": f"# {candidate_id}\n",
                    "metrics": {"combined_score": score, "worst_return": score},
                }))
            index = json.loads(export_top_candidates(checkpoint, root).read_text())
            self.assertEqual([item["candidate_id"] for item in index], ["b", "a"])

    def test_run_config_uses_absolute_template_directory(self):
        from evolution.config import write_run_config

        with tempfile.TemporaryDirectory() as directory:
            path, run_dir = write_run_config(
                Path(directory), "BTCUSDT.BINANCE", "r1", 30, random_seed=17,
            )
            config = yaml.safe_load(path.read_text())
            metadata = json.loads((run_dir / "run-metadata.json").read_text())
            snapshot = json.loads((run_dir / "config.redacted.json").read_text())
        template_dir = Path(config["prompt"]["template_dir"])
        self.assertTrue(template_dir.is_absolute())
        self.assertTrue((template_dir / "system_message.txt").is_file())
        self.assertEqual(metadata["random_seed"], 17)
        self.assertEqual(metadata["budget_stage"], "search_smoke")
        self.assertEqual(snapshot["run_metadata"], metadata)

    def test_budget_policy_rejects_unsupported_and_unadvanced_budgets(self):
        from evolution.budget_policy import validate_budget

        for iterations in (1, 20, 101, 299, 301):
            with self.subTest(iterations=iterations), self.assertRaises(ValueError):
                validate_budget(iterations)
        with self.assertRaisesRegex(ValueError, "advancement record"):
            validate_budget(300)

    def test_budget_policy_accepts_viability_without_discovery_evidence(self):
        from evolution.budget_policy import validate_budget

        self.assertEqual(validate_budget(10).value, "lifecycle")
        self.assertEqual(validate_budget(30).value, "search_smoke")
        self.assertEqual(validate_budget(50).value, "viability")
        self.assertEqual(validate_budget(100).value, "viability")

    def test_extended_budget_requires_and_accepts_registered_record(self):
        from evolution.budget_policy import BUDGET_POLICY_NAME
        from evolution.budget_policy import validate_budget

        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory) / "advance.json"
            record.write_text(json.dumps({
                "policy": BUDGET_POLICY_NAME,
                "target_stage": "extended",
                "approved": True,
            }))
            self.assertEqual(validate_budget(300, advancement_record=record).value, "extended")

    def test_cli_accepts_explicit_seed_and_budget_stage(self):
        from evolution.__main__ import parse_args
        from unittest.mock import patch

        with patch("sys.argv", [
            "evolution", "evolve", "--instrument-id", "BTCUSDT.BINANCE",
            "--run-id", "r1", "--iterations", "50", "--seed", "23",
            "--budget-stage", "viability",
        ]):
            args = parse_args()
        self.assertEqual(args.random_seed, 23)
        self.assertEqual(args.budget_stage, "viability")

    @patch("evolution.runner.subprocess.run")
    def test_429_preserves_checkpoint_and_redacts_key(self, run):
        from evolution.runner import run_evolution

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"OPENROUTER_API_KEY": "private-key"}, clear=False):
            root = Path(directory)
            dataset = root / "data"
            for fold in range(1, 6):
                target = dataset / f"discovery_{fold}" / "BTCUSDT.BINANCE"
                target.mkdir(parents=True)
                (target / "manifest.json").write_text("{}")
            output = root / "out"
            run.return_value = subprocess.CompletedProcess([], 1, "429 quota private-key", "")
            result = run_evolution("BTCUSDT.BINANCE", dataset, output, "r1")
            self.assertTrue(result.rate_limited)
            self.assertNotIn("private-key", (result.output_directory / "runner.log").read_text())
            passed_env = run.call_args.kwargs["env"]
            self.assertEqual(Path(passed_env["PYTHONPATH"]), Path.cwd())
            self.assertNotIn("CATALOG_S3_SECRET_KEY", passed_env)


if __name__ == "__main__":
    unittest.main()
