import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class EvolutionFamilyTests(unittest.TestCase):
    def test_registry_has_exactly_three_families_and_instrument_rules(self):
        from evolution.families import FAMILY_REGISTRY, validate_family_instrument

        self.assertEqual(set(FAMILY_REGISTRY), {
            "trend-flow-confirmation-v1",
            "down-streak-risk-off-btc-v1",
            "pullback-exhaustion-v1",
        })
        validate_family_instrument("trend-flow-confirmation-v1", "ETHUSDT.BINANCE")
        validate_family_instrument("down-streak-risk-off-btc-v1", "BTCUSDT.BINANCE")
        with self.assertRaises(ValueError):
            validate_family_instrument("down-streak-risk-off-btc-v1", "ETHUSDT.BINANCE")

    def test_each_seed_resets_state_and_produces_identical_outputs(self):
        from evolution.backtest import run_candidate
        from evolution.families import FAMILY_REGISTRY
        from evolution.market_state import EvolutionMarketState
        from evolution.sandbox_worker import _synthetic_states

        self.assertEqual(len(EvolutionMarketState.FIELDS), 32)
        self.assertIn("return_5m", EvolutionMarketState.FIELDS)
        self.assertIn("relative_spread_15m", EvolutionMarketState.FIELDS)
        for family in FAMILY_REGISTRY.values():
            instrument = family.allowed_instruments[0]
            first = run_candidate(family.seed_program, instrument, _synthetic_states(instrument))
            second = run_candidate(family.seed_program, instrument, _synthetic_states(instrument))
            self.assertEqual(first.metrics, second.metrics, family.family_id)
            self.assertEqual(first.fill_count, second.fill_count, family.family_id)
            self.assertEqual(first.position_count, second.position_count, family.family_id)
            source = family.seed_program.read_text(encoding="utf-8")
            from evolution.candidate import validate_candidate_file
            validation = validate_candidate_file(family.seed_program, family.seed_program, family.family_id)
            self.assertTrue(validation.valid, validation.errors)
            self.assertIn("class EvolvedStrategy(RuleInterpreterStrategy)", source)
            module = __import__("importlib.util").util.spec_from_file_location("seed", family.seed_program)
            loaded = __import__("importlib.util").util.module_from_spec(module)
            module.loader.exec_module(loaded)
            strategy = loaded.EvolvedStrategy.__new__(loaded.EvolvedStrategy)
            for name in ("entry_confirmations", "exit_confirmations", "hold_bars", "cooldown_bars"):
                setattr(strategy, name, 2)
            strategy.on_reset()
            self.assertEqual(strategy.entry_confirmations, 0)
            self.assertEqual(strategy.exit_confirmations, 0)
            self.assertEqual(strategy.hold_bars, 0)
            self.assertEqual(strategy.cooldown_bars, 0)

    def test_pullback_seed_uses_exact_four_feature_recovery_rule(self):
        from evolution.families import FAMILY_REGISTRY
        from evolution.rules import validate_rule_source

        source = FAMILY_REGISTRY["pullback-exhaustion-v1"].seed_program
        result = validate_rule_source(source)
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(
            [condition.feature for condition in result.spec.entry.conditions],
            ["return_60m", "return_5m", "close_location", "signed_flow_persistence_5m"],
        )
        self.assertEqual(result.spec.entry.confirmations, 2)
        self.assertEqual(result.spec.exit.mode, "any")
        self.assertEqual(result.spec.exit.min_hold_bars, 10)

    @patch("evolution.runner.subprocess.run")
    def test_family_run_copies_seed_and_writes_hash_metadata(self, run):
        from evolution.families import FAMILY_REGISTRY
        from evolution.runner import run_evolution

        family = FAMILY_REGISTRY["trend-flow-confirmation-v1"]
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"OPENROUTER_API_KEY": "key"}, clear=False
        ):
            root = Path(directory)
            dataset = root / "data"
            for fold in range(1, 6):
                target = dataset / f"discovery_{fold}" / "BTCUSDT.BINANCE"
                target.mkdir(parents=True)
                (target / "manifest.json").write_text("{}")
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            result = run_evolution(
                "BTCUSDT.BINANCE", dataset, root / "out", "r1", family=family,
            )
            metadata = json.loads((result.output_directory / "run_metadata.json").read_text())
            self.assertEqual(metadata["family_id"], family.family_id)
            self.assertEqual(metadata["hypothesis"], family.hypothesis)
            self.assertEqual(metadata["instrument_id"], "BTCUSDT.BINANCE")
            self.assertEqual(metadata["budget_stage"], "search_smoke")
            self.assertEqual(metadata["random_seed"], 20260829)
            budget_metadata = json.loads((result.output_directory / "run-metadata.json").read_text())
            self.assertEqual(budget_metadata, metadata)
            self.assertEqual(metadata["seed_program_sha256"], hashlib.sha256(
                family.seed_program.read_bytes()
            ).hexdigest())
            self.assertEqual(len(metadata["composed_prompt_sha256"]), 64)
            system_prompt = (result.output_directory / "prompts/system_message.txt").read_text()
            diff_prompt = (result.output_directory / "prompts/diff_user.txt").read_text()
            self.assertIn(family.prompt_context, system_prompt)
            self.assertNotIn(family.prompt_context, diff_prompt)
            self.assertNotIn("close/open/high/low", system_prompt)
            self.assertNotIn("spread_bps as an execution filter", system_prompt)
            command = run.call_args.args[0]
            self.assertEqual(Path(command[3]), result.output_directory / "initial_program.py")

    @patch("evolution.runner.subprocess.run")
    def test_legacy_run_keeps_reference_program_and_prompts(self, run):
        from evolution.runner import run_evolution

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"OPENROUTER_API_KEY": "key"}, clear=False
        ):
            root = Path(directory)
            dataset = root / "data"
            for fold in range(1, 6):
                target = dataset / f"discovery_{fold}" / "BTCUSDT.BINANCE"
                target.mkdir(parents=True)
                (target / "manifest.json").write_text("{}")
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            result = run_evolution("BTCUSDT.BINANCE", dataset, root / "out", "r1")
            self.assertEqual(Path(run.call_args.args[0][3]), Path("evolution/initial_program.py").resolve())
            metadata = json.loads((result.output_directory / "run_metadata.json").read_text())
            self.assertNotIn("family_id", metadata)
            self.assertEqual(metadata["random_seed"], 20260829)
            self.assertEqual(metadata["budget_stage"], "search_smoke")

    def test_invalid_family_instrument_is_rejected_before_openevolve(self):
        from evolution.runner import run_evolution

        with patch("evolution.runner.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "not allowed"):
                run_evolution(
                    "ETHUSDT.BINANCE", Path("missing"), Path("out"), "r1",
                    family="down-streak-risk-off-btc-v1",
                )
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
