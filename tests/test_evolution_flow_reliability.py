import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class FlowReliabilityTests(unittest.TestCase):
    @patch("evolution.dataset.verify_manifest")
    @patch("evolution.sandbox.subprocess.run")
    def test_preflight_checks_only_discovery_and_local_image(self, run, verify):
        from evolution.sandbox import DEFAULT_IMAGE, preflight_sandbox
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        preflight_sandbox(Path("fixture"), "BTCUSDT.BINANCE", DEFAULT_IMAGE)
        self.assertEqual([call.args[2] for call in verify.call_args_list],
                         [f"discovery_{i}" for i in range(1, 6)])
        self.assertEqual(run.call_args_list[-1].args[0],
                         ["docker", "image", "inspect", "alpha-evolution-sandbox:0.2"])

    @patch("evolution.dataset.verify_manifest")
    @patch("evolution.sandbox.subprocess.run")
    def test_preflight_daemon_error_stops(self, run, verify):
        from evolution.sandbox import preflight_sandbox
        run.return_value = subprocess.CompletedProcess([], 1, "", "daemon unavailable")
        with self.assertRaisesRegex(RuntimeError, "preflight"):
            preflight_sandbox(Path("fixture"), "BTCUSDT.BINANCE", "image")
        self.assertEqual(run.call_count, 1)

    def test_missing_metadata_is_unknown_and_infrastructure_is_distinct(self):
        from evolution.lifecycle_summary import _classify_events
        log = "Iteration 1: Program p (parent: seed) completed"
        self.assertEqual(_classify_events([log], {})[0]["category"], "unknown_candidate")
        payload = {"p": {"metrics": {"combined_score": -1000000, "infrastructure_error": 1}}}
        self.assertEqual(_classify_events([log], payload)[0]["category"], "infrastructure_error")

    def test_latest_source_checkpoint_uses_numeric_order(self):
        from evolution.lifecycle_summary import _source_uniqueness
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for iteration, code in ((30, "bad("), (100, "x = 1")):
                programs = root / "checkpoints" / f"checkpoint_{iteration}" / "programs"
                programs.mkdir(parents=True)
                (programs / "p.json").write_text(json.dumps({"id": "p", "code": code}))
            result = _source_uniqueness(root)
        self.assertEqual(result["invalid_signature_count"], 0)
        self.assertEqual(result["valid_signature_count"], 1)

    @patch("evolution.evaluator.run_sandbox")
    def test_infrastructure_error_has_distinct_flag_and_safe_score(self, sandbox):
        from evolution.evaluator import evaluate
        from evolution.sandbox import SandboxResult
        sandbox.return_value = SandboxResult(125, None, "missing image")
        with patch.dict("os.environ", {"EVOLUTION_DATASET_ROOT": "/fixture",
                                      "EVOLUTION_INSTRUMENT_ID": "BTCUSDT.BINANCE",
                                      "EVOLUTION_FAMILY_ID": "",
                                      "EVOLUTION_REFERENCE_PROGRAM": "evolution/initial_program.py"}):
            result = evaluate("evolution/initial_program.py")
        self.assertEqual(result.metrics["infrastructure_error"], 1)
        self.assertEqual(result.metrics["combined_score"], -1000000)

    @patch("evolution.sandbox.subprocess.run")
    def test_timeout_cleanup_failure_preserves_original_error(self, run):
        from evolution.sandbox import run_sandbox
        run.side_effect = subprocess.TimeoutExpired("docker", 1)
        result = run_sandbox(Path("candidate"), Path("fixture"), "BTCUSDT.BINANCE")
        self.assertEqual(result.error, "sandbox timeout")
