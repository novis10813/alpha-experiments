import hashlib
import json
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


class EvolutionRunnerTests(unittest.TestCase):
    @staticmethod
    def _dataset(root: Path) -> Path:
        dataset = root / "data"
        for fold in range(1, 6):
            target = dataset / f"discovery_{fold}" / "BTCUSDT.BINANCE"
            target.mkdir(parents=True)
            (target / "manifest.json").write_text("{}")
        return dataset

    @staticmethod
    def _checkpoint(run_dir: Path, iteration: int) -> Path:
        checkpoint = run_dir / "checkpoints" / f"checkpoint_{iteration}"
        (checkpoint / "programs").mkdir(parents=True, exist_ok=True)
        (checkpoint / "metadata.json").write_text(json.dumps({"last_iteration": iteration}))
        return checkpoint

    @staticmethod
    def _stream_result(output: str = "", returncode: int = 0):
        completed = subprocess.CompletedProcess([], returncode, output, "")
        return completed, output, Path("attempt.log")

    @staticmethod
    def _accepted_output(iteration: int) -> str:
        return f"Iteration {iteration}: Program accepted (parent: seed) completed\n"

    def _runner_patches(self, stream_result):
        return (
            patch.dict(os.environ, {"VLLM_API_KEY": "test-key"}, clear=False),
            patch("evolution.runner._load_dotenv"),
            patch("evolution.runner.preflight_sandbox"),
            patch("evolution.runner._run_streaming", return_value=stream_result),
        )

    def test_base_config_uses_only_vllm_and_preserves_search_plan(self):
        from evolution.config import load_base_config

        config = load_base_config()
        self.assertEqual(config["llm"]["api_base"], "http://100.83.39.100:11432/v1")
        self.assertEqual(
            [model["name"] for model in config["llm"]["models"]],
            ["qwen3.8-27b"],
        )
        self.assertEqual([model["weight"] for model in config["llm"]["models"]], [1.0])
        self.assertEqual(config["llm"]["api_key"], "${VLLM_API_KEY}")
        self.assertEqual(config["llm"]["reasoning_effort"], "none")
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

    def test_run_config_uses_absolute_template_directory_and_hashes_config(self):
        from evolution.config import write_run_config

        with tempfile.TemporaryDirectory() as directory:
            path, run_dir = write_run_config(Path(directory), "BTCUSDT.BINANCE", "r1", 30, random_seed=17)
            config = yaml.safe_load(path.read_text())
            metadata = json.loads((run_dir / "run-metadata.json").read_text())
            snapshot = json.loads((run_dir / "config.redacted.json").read_text())
            state = json.loads((run_dir / "execution-state.json").read_text())
            config_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertTrue(Path(config["prompt"]["template_dir"]).is_absolute())
        self.assertEqual(metadata["random_seed"], 17)
        self.assertEqual(metadata["budget_stage"], "search_smoke")
        self.assertEqual(metadata["config_sha256"], config_hash)
        self.assertEqual(snapshot["run_metadata"], metadata)
        self.assertEqual(state["approved_target_iterations"], 30)

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

        with patch("sys.argv", [
            "evolution", "evolve", "--instrument-id", "BTCUSDT.BINANCE",
            "--run-id", "r1", "--iterations", "50", "--seed", "23",
            "--budget-stage", "viability",
        ]):
            args = parse_args()
        self.assertEqual(args.random_seed, 23)
        self.assertEqual(args.budget_stage, "viability")

    def test_429_preserves_checkpoint_and_redacts_key(self):
        from evolution.runner import run_evolution

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = self._dataset(root)

            def streaming(command, run_dir, env, secret):
                run_dir.mkdir(parents=True, exist_ok=True)
                redacted = "429 quota [REDACTED]"
                (run_dir / "runner.log").write_text(redacted)
                return self._stream_result(redacted, 1)

            with patch.dict(os.environ, {"VLLM_API_KEY": "test-key"}, clear=False), \
                    patch("evolution.runner._load_dotenv"), \
                    patch("evolution.runner.preflight_sandbox") as preflight, \
                    patch("evolution.runner._run_streaming", side_effect=streaming) as runner:
                result = run_evolution("BTCUSDT.BINANCE", dataset, root / "out", "r1")
            self.assertTrue(result.rate_limited)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.process_returncode, 1)
            self.assertNotIn("test-key", (result.output_directory / "runner.log").read_text())
            passed_env = runner.call_args.args[2]
            self.assertEqual(Path(passed_env["PYTHONPATH"]), Path.cwd())
            self.assertNotIn("CATALOG_S3_SECRET_KEY", passed_env)
            preflight.assert_called_once()

    def test_preflight_failure_does_not_create_fresh_run_snapshot(self):
        from evolution.runner import run_evolution

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = self._dataset(root)
            with patch.dict(os.environ, {"VLLM_API_KEY": "key"}, clear=False), \
                    patch("evolution.runner._load_dotenv"), \
                    patch("evolution.runner.preflight_sandbox", side_effect=RuntimeError("no image")), \
                    patch("evolution.runner._run_streaming") as streaming:
                with self.assertRaisesRegex(RuntimeError, "no image"):
                    run_evolution("BTCUSDT.BINANCE", dataset, root / "out", "r1")
            self.assertFalse((root / "out" / "btcusdt" / "r1").exists())
            streaming.assert_not_called()

    def test_30_to_100_resume_submits_only_70_and_preserves_config_snapshot(self):
        from evolution.runner import run_evolution

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = self._dataset(root)
            output = root / "out"
            calls = []

            def streaming(command, run_dir, env, secret):
                calls.append(command)
                target = 30 if len(calls) == 1 else 100
                self._checkpoint(run_dir, target)
                text = self._accepted_output(target)
                return self._stream_result(text)

            with patch.dict(os.environ, {"VLLM_API_KEY": "key"}, clear=False), \
                    patch("evolution.runner._load_dotenv"), \
                    patch("evolution.runner.preflight_sandbox"), \
                    patch("evolution.runner._run_streaming", side_effect=streaming):
                first = run_evolution("BTCUSDT.BINANCE", dataset, output, "r1", iterations=30)
                original_config = (first.output_directory / "openevolve.yaml").read_bytes()
                resumed = run_evolution(
                    "BTCUSDT.BINANCE", dataset, output, "r1", iterations=100, checkpoint=first.checkpoint,
                )
            command = calls[1]
            self.assertEqual(command[command.index("--iterations") + 1], "70")
            self.assertEqual((resumed.output_directory / "openevolve.yaml").read_bytes(), original_config)
            state = json.loads((resumed.output_directory / "execution-state.json").read_text())
            self.assertEqual(state["approved_target_iterations"], 100)
            self.assertEqual(state["attempts"][-1]["target_iterations"], 100)

    def test_resume_default_target_uses_last_approved_budget_and_noops_when_complete(self):
        from evolution.runner import run_evolution

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = self._dataset(root)
            output = root / "out"
            calls = []

            def streaming(command, run_dir, env, secret):
                calls.append(command)
                checkpoint = 30 if len(calls) == 1 else 100
                self._checkpoint(run_dir, checkpoint)
                text = self._accepted_output(checkpoint)
                return self._stream_result(text)

            with patch.dict(os.environ, {"VLLM_API_KEY": "key"}, clear=False), \
                    patch("evolution.runner._load_dotenv"), \
                    patch("evolution.runner.preflight_sandbox"), \
                    patch("evolution.runner._run_streaming", side_effect=streaming):
                first = run_evolution("BTCUSDT.BINANCE", dataset, output, "r1", iterations=30)
                run_evolution("BTCUSDT.BINANCE", dataset, output, "r1", iterations=100, checkpoint=first.checkpoint)
                result = run_evolution("BTCUSDT.BINANCE", dataset, output, "r1", checkpoint=self._checkpoint(first.output_directory, 100))
            self.assertEqual(result.returncode, 0)
            self.assertEqual(len(calls), 2)

    def test_quoted_resume_command_validates_through_cli_parser(self):
        from evolution.__main__ import parse_args
        from evolution.runner import resume_command

        command = resume_command(
            "BTCUSDT.BINANCE", Path("data with spaces"), Path("output with spaces"),
            "run with spaces", 100, Path("checkpoint with spaces"), random_seed=7,
        )
        tokens = shlex.split(command)
        with patch("sys.argv", ["evolution", *tokens[5:]]):
            args = parse_args()
        self.assertEqual(args.dataset_root, Path("data with spaces"))
        self.assertEqual(args.output_root, Path("output with spaces"))
        self.assertEqual(args.run_id, "run with spaces")
        self.assertEqual(args.checkpoint, Path("checkpoint with spaces"))
        self.assertEqual(args.random_seed, 7)

    def test_resume_identity_mismatch_does_not_write_files(self):
        from evolution.config import write_run_config
        from evolution.runner import run_evolution

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = self._dataset(root)
            output = root / "out"
            _, run_dir = write_run_config(output, "BTCUSDT.BINANCE", "r1", 30, dataset_root=dataset)
            checkpoint = self._checkpoint(run_dir, 10)
            before = {path.name: path.read_bytes() for path in run_dir.iterdir() if path.is_file()}
            (dataset / "discovery_1" / "BTCUSDT.BINANCE" / "manifest.json").write_text("tampered")
            with patch.dict(os.environ, {"VLLM_API_KEY": "key"}, clear=False), \
                    patch("evolution.runner._load_dotenv"), \
                    patch("evolution.runner.preflight_sandbox"), \
                    patch("evolution.runner._run_streaming") as streaming:
                with self.assertRaisesRegex(RuntimeError, "dataset identity"):
                    run_evolution("BTCUSDT.BINANCE", dataset, output, "r1", checkpoint=checkpoint)
            after = {path.name: path.read_bytes() for path in run_dir.iterdir() if path.is_file()}
            self.assertEqual(before, after)
            streaming.assert_not_called()

    def test_fresh_duplicate_protection_runs_no_second_process(self):
        from evolution.runner import run_evolution

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = self._dataset(root)
            patches = self._runner_patches(self._stream_result(self._accepted_output(1)))
            with patches[0], patches[1], patches[2], patches[3] as streaming:
                run_evolution("BTCUSDT.BINANCE", dataset, root / "out", "r1")
                with self.assertRaises(FileExistsError):
                    run_evolution("BTCUSDT.BINANCE", dataset, root / "out", "r1")
            self.assertEqual(streaming.call_count, 1)

    def test_recovered_429_with_accepted_iteration_is_workflow_success(self):
        from evolution.runner import run_evolution

        output = "HTTP/1.1 429 Too Many Requests\n" + self._accepted_output(1)
        with tempfile.TemporaryDirectory() as directory:
            patches = self._runner_patches(self._stream_result(output, 0))
            with patches[0], patches[1], patches[2], patches[3], patch(
                "evolution.runner._load_programs",
                return_value={"accepted": {"metrics": {"combined_score": 1.0}}},
            ):
                result = run_evolution(
                    "BTCUSDT.BINANCE", self._dataset(Path(directory)), Path(directory) / "out", "r1",
                )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.process_returncode, 0)

    def test_all_429_with_zero_process_returncode_is_workflow_failure(self):
        from evolution.runner import run_evolution

        with tempfile.TemporaryDirectory() as directory:
            patches = self._runner_patches(self._stream_result("429 retry exhausted\n", 0))
            with patches[0], patches[1], patches[2], patches[3]:
                result = run_evolution(
                    "BTCUSDT.BINANCE", self._dataset(Path(directory)), Path(directory) / "out", "r1",
                )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.process_returncode, 0)

    def test_streaming_redacts_secrets_from_attempt_and_runner_logs(self):
        from evolution.runner import _run_streaming

        class FakePopen:
            pid = 123

            def __init__(self, *args, **kwargs):
                self.stdout = iter(["hello secret\n", "done\n"])

            def wait(self, *args, **kwargs):
                return 0

        with tempfile.TemporaryDirectory() as directory, patch("evolution.runner.subprocess.Popen", FakePopen):
            run_dir = Path(directory)
            completed, output, attempt = _run_streaming(["fake"], run_dir, {}, "secret")
            self.assertEqual(completed.returncode, 0)
            self.assertNotIn("secret", output)
            self.assertNotIn("secret", attempt.read_text())
            self.assertNotIn("secret", (run_dir / "runner.log").read_text())

    def test_streaming_interrupt_terminates_process_group_and_returns_130(self):
        from evolution.runner import _run_streaming

        class InterruptingStream:
            def __iter__(self):
                raise KeyboardInterrupt
                yield "never"

        class FakePopen:
            pid = 123

            def __init__(self, *args, **kwargs):
                self.stdout = InterruptingStream()

        with tempfile.TemporaryDirectory() as directory, patch("evolution.runner.subprocess.Popen", FakePopen), \
                patch("evolution.runner._terminate_process_group") as terminate:
            completed, output, attempt = _run_streaming(["fake"], Path(directory), {}, "secret")
            self.assertEqual(completed.returncode, 130)
            terminate.assert_called_once()
            self.assertIn("interrupted", attempt.read_text())

    def test_resume_rejects_run_id_mismatch(self):
        from evolution.config import write_run_config
        from evolution.runner import run_evolution

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = self._dataset(root)
            output = root / "out"
            _, run_dir = write_run_config(output, "BTCUSDT.BINANCE", "r1", 30, dataset_root=dataset)
            checkpoint = self._checkpoint(run_dir, 10)
            metadata_path = run_dir / "run_metadata.json"
            metadata = json.loads(metadata_path.read_text())
            metadata["run_id"] = "other"
            metadata_path.write_text(json.dumps(metadata))
            with patch.dict(os.environ, {"VLLM_API_KEY": "key"}, clear=False), \
                    patch("evolution.runner._load_dotenv"), \
                    patch("evolution.runner.preflight_sandbox"), \
                    patch("evolution.runner._run_streaming"):
                with self.assertRaisesRegex(RuntimeError, "run_id"):
                    run_evolution("BTCUSDT.BINANCE", dataset, output, "r1", checkpoint=checkpoint)


if __name__ == "__main__":
    unittest.main()
