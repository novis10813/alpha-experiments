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
            self.assertIn("def on_reset", source)
            self.assertIn("self.closes.clear()", source)
            module = __import__("importlib.util").util.spec_from_file_location("seed", family.seed_program)
            loaded = __import__("importlib.util").util.module_from_spec(module)
            module.loader.exec_module(loaded)
            strategy = loaded.EvolvedStrategy.__new__(loaded.EvolvedStrategy)
            strategy.closes = __import__("collections").deque([1.0])
            for name in ("entry_confirmations", "exit_confirmations", "hold_bars", "cooldown_bars"):
                setattr(strategy, name, 2)
            if hasattr(strategy, "down_streak"):
                strategy.down_streak = 2
            if hasattr(strategy, "pullback_bars"):
                strategy.pullback_bars = 2
            strategy.on_reset()
            self.assertEqual(tuple(strategy.closes), ())
            self.assertEqual(strategy.entry_confirmations, 0)
            self.assertEqual(strategy.exit_confirmations, 0)
            self.assertEqual(strategy.hold_bars, 0)
            self.assertEqual(strategy.cooldown_bars, 0)

    def test_pullback_requires_new_pullback_after_exit_and_cooldown(self):
        from collections import deque
        from evolution.families import FAMILY_REGISTRY

        source = FAMILY_REGISTRY["pullback-exhaustion-v1"].seed_program
        module_spec = __import__("importlib.util").util.spec_from_file_location("pullback", source)
        module = __import__("importlib.util").util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        strategy = SimpleNamespace(
            closes=deque(maxlen=20), pullback_bars=0, entry_confirmations=0,
            exit_confirmations=0, hold_bars=0, cooldown_bars=0,
            config=SimpleNamespace(instrument_id="BTCUSDT.BINANCE"),
        )
        entries = []
        exits = []
        flat = [True]

        class Portfolio:
            def is_flat(self, _instrument_id):
                return flat[0]

            def is_net_long(self, _instrument_id):
                return not flat[0]

        strategy.portfolio = Portfolio()
        strategy.enter_long = lambda price: (entries.append(price), flat.__setitem__(0, False))
        strategy.exit_long = lambda: (exits.append(True), flat.__setitem__(0, True))

        def state(close, imbalance):
            return SimpleNamespace(
                close=close, trade_imbalance=imbalance, depth10_obi_last=0.0,
            )

        on_data = module.EvolvedStrategy.on_data
        for _ in range(10):
            on_data(strategy, state(100.0, 1.0))
        on_data(strategy, state(99.0, -1.0))
        on_data(strategy, state(100.0, 1.0))
        on_data(strategy, state(100.0, 1.0))
        self.assertEqual(len(entries), 1)
        self.assertEqual(strategy.pullback_bars, 0)

        for _ in range(5):
            on_data(strategy, state(90.0, 1.0))
        on_data(strategy, state(90.0, 1.0))
        self.assertEqual(len(exits), 1)
        for _ in range(4):
            on_data(strategy, state(101.0, 1.0))
        self.assertEqual(len(entries), 1)

        on_data(strategy, state(99.0, -1.0))
        on_data(strategy, state(101.0, 1.0))
        on_data(strategy, state(101.0, 1.0))
        self.assertEqual(len(entries), 2)

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
            self.assertIn(family.prompt_context, (result.output_directory / "prompts/system_message.txt").read_text())
            self.assertNotIn(family.prompt_context, (result.output_directory / "prompts/diff_user.txt").read_text())
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
