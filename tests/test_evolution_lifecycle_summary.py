import json
import tempfile
import unittest
from pathlib import Path


class EvolutionLifecycleSummaryTests(unittest.TestCase):
    def test_prompt_renders_inspiration_without_fragment_formatting_error(self):
        from evolution.config import write_run_config
        from evolution.families import FAMILY_REGISTRY
        from openevolve.config import PromptConfig
        from openevolve.prompt.sampler import PromptSampler

        family = FAMILY_REGISTRY["trend-flow-confirmation-v1"]
        with tempfile.TemporaryDirectory() as directory:
            config_path, run_directory = write_run_config(
                Path(directory), "BTCUSDT.BINANCE", "prompt-test", 10, family=family,
            )
            del config_path
            prompt_config = PromptConfig(
                template_dir=str(run_directory / "prompts"),
                use_template_stochasticity=False,
            )
            prompt = PromptSampler(prompt_config).build_prompt(
                current_program=family.seed_program.read_text(encoding="utf-8"),
                program_metrics={"combined_score": 0.5},
                inspirations=[{
                    "id": "inspiration-1",
                    "code": family.seed_program.read_text(encoding="utf-8"),
                    "metrics": {"combined_score": 0.95},
                }],
            )

        rendered = prompt["user"]
        self.assertNotIn("[Fragment formatting error", rendered)
        self.assertNotIn("metric_name", rendered)
        self.assertIn("combined_score", rendered)

    def test_family_prompt_is_strict_but_legacy_prompt_is_unchanged(self):
        from evolution.config import write_run_config
        from evolution.families import FAMILY_REGISTRY

        family = FAMILY_REGISTRY["trend-flow-confirmation-v1"]
        with tempfile.TemporaryDirectory() as directory:
            _, run_directory = write_run_config(
                Path(directory), "BTCUSDT.BINANCE", "strict-test", 10, family=family,
            )
            family_prompt = (run_directory / "prompts/diff_user.txt").read_text(encoding="utf-8")

        legacy_prompt = Path("evolution/prompts/diff_user.txt").read_text(encoding="utf-8")
        self.assertIn("response must start with `<<<<<<< SEARCH`", family_prompt)
        self.assertIn("exactly one SEARCH/REPLACE block", family_prompt)
        self.assertIn("Do not include an", family_prompt)
        self.assertNotIn("Briefly explain the market-structure hypothesis", family_prompt)
        self.assertIn("Briefly explain the market-structure hypothesis", legacy_prompt)

    def test_summary_classifies_fixture_events_and_source_uniqueness(self):
        from evolution.lifecycle_summary import summarize_lifecycle
        from evolution.metrics import REJECTED_SCORE

        source_a = """class EvolvedStrategy:\n# EVOLVE-BLOCK-START\n    value = 1\n# EVOLVE-BLOCK-END\n"""
        source_b = """class EvolvedStrategy:\n# EVOLVE-BLOCK-START\n    # equivalent formatting\n    value=1\n# EVOLVE-BLOCK-END\n"""
        with tempfile.TemporaryDirectory() as directory:
            run_directory = Path(directory)
            (run_directory / "logs").mkdir()
            (run_directory / "checkpoints/checkpoint_10/programs").mkdir(parents=True)
            programs = [
                {"id": "accepted", "code": source_a, "metrics": {"combined_score": 1.0}},
                {"id": "rejected", "code": source_b, "metrics": {"combined_score": REJECTED_SCORE}},
            ]
            for program in programs:
                (run_directory / "checkpoints/checkpoint_10/programs" / f"{program['id']}.json").write_text(
                    json.dumps(program), encoding="utf-8",
                )
            (run_directory / "logs/run.log").write_text(
                "\n".join([
                    "Iteration 1: Program accepted (parent: seed) completed",
                    "Iteration 2 error: No valid diffs found in response",
                    "Timeout on attempt 2/2",
                    "All 2 attempts failed with timeout",
                    "Iteration 3 error: LLM generation failed: ",
                    'HTTP/1.1 404 Not Found',
                    "Iteration 4 error: LLM generation failed: Error code: 404",
                    "Iteration 5: Program rejected (parent: seed) completed",
                ]),
                encoding="utf-8",
            )
            summary = summarize_lifecycle(run_directory)
            written = json.loads((run_directory / "lifecycle-summary.json").read_text())

        self.assertEqual(summary, written)
        self.assertEqual(summary["attempted_iterations"], 5)
        self.assertEqual(summary["category_counts"]["accepted_candidate"], 1)
        self.assertEqual(summary["category_counts"]["diff_parse_failure"], 1)
        self.assertEqual(summary["category_counts"]["provider_timeout"], 1)
        self.assertEqual(summary["category_counts"]["provider_http_error"], 1)
        self.assertEqual(summary["category_counts"]["evaluator_candidate_rejection"], 1)
        uniqueness = summary["semantic_source_uniqueness"]
        self.assertEqual(uniqueness["program_count"], 2)
        self.assertEqual(uniqueness["valid_signature_count"], 1)
        self.assertEqual(uniqueness["duplicate_groups"], [["accepted", "rejected"]])


if __name__ == "__main__":
    unittest.main()
