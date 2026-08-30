import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SandboxTests(unittest.TestCase):
    def test_docker_build_context_excludes_local_secrets(self):
        contents = Path(".dockerignore").read_text(encoding="utf-8")
        self.assertIn(".env", contents.splitlines())
        self.assertEqual(contents.splitlines()[0], "*")

    def test_command_has_all_isolation_controls_and_no_secret_environment(self):
        from evolution.sandbox import docker_command

        command = docker_command(Path("candidate.py"), Path("dataset"), "BTCUSDT.BINANCE", container_name="fixed")
        joined = " ".join(command)
        for expected in ("--network none", "--read-only", "--cpus 1", "--memory 1g", "--cap-drop ALL", "no-new-privileges:true", "readonly"):
            self.assertIn(expected, joined)
        self.assertNotIn("OPENROUTER", joined)
        self.assertNotIn("CATALOG_S3", joined)
        self.assertNotIn("/validation", joined)
        self.assertNotIn("/holdout", joined)
        self.assertEqual(joined.count("dst=/dataset/discovery_"), 5)

    @patch("evolution.sandbox.subprocess.run")
    def test_success_parses_json(self, run):
        from evolution.sandbox import run_sandbox

        run.return_value = subprocess.CompletedProcess([], 0, json.dumps({"ok": True}), "")
        result = run_sandbox(Path("candidate.py"), Path("dataset"), "BTCUSDT.BINANCE")
        self.assertEqual(result.payload, {"ok": True})

    @patch("evolution.sandbox.subprocess.run")
    def test_timeout_forces_container_removal(self, run):
        from evolution.sandbox import run_sandbox

        run.side_effect = [subprocess.TimeoutExpired([], 1), subprocess.CompletedProcess([], 0, "", "")]
        result = run_sandbox(Path("candidate.py"), Path("dataset"), "BTCUSDT.BINANCE", timeout_seconds=1)
        self.assertEqual(result.returncode, 124)
        self.assertEqual(run.call_args_list[1].args[0][1:3], ["rm", "-f"])


if __name__ == "__main__":
    unittest.main()
