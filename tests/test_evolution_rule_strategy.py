from __future__ import annotations

from collections import deque
from types import SimpleNamespace
import unittest

from evolution.initial_program import EvolutionStrategyConfig
from evolution.instruments import build_bar_type
from evolution.market_state import EvolutionMarketState
from evolution.rules.strategy import RuleInterpreterStrategy
from nautilus_trader.model.data import DataType
from nautilus_trader.model.identifiers import InstrumentId


class _Portfolio:
    def __init__(self) -> None:
        self.flat = True

    def is_flat(self, _instrument_id: str) -> bool:
        return self.flat

    def is_net_long(self, _instrument_id: str) -> bool:
        return not self.flat


class _RuleHarness(RuleInterpreterStrategy):
    RULE_SPEC = {
        "entry": [{"field": "close", "operator": "gte", "value": 100.0}],
        "entry_confirmations": 2,
        "exit": {
            "mode": "all",
            "conditions": [
                {"field": "close", "operator": "lt", "value": 99.0},
                {"field": "trade_imbalance", "operator": "lt", "value": 0.0},
            ],
        },
        "exit_confirmations": 2,
        "min_hold_bars": 2,
        "cooldown_bars": 3,
    }

    @property
    def portfolio(self):
        return self._test_portfolio

    def enter_long(self, price: float) -> None:
        if self._test_portfolio.flat:
            self.entries.append(price)
            self._test_portfolio.flat = False

    def exit_long(self) -> None:
        if not self._test_portfolio.flat:
            self.exits += 1
            self._test_portfolio.flat = True


def _state(close: float, trade_imbalance: float = 1.0, ts: int = 1) -> EvolutionMarketState:
    return EvolutionMarketState(
        "BTCUSDT.BINANCE", close, close, close, close, 1.0, 1, 1, 0,
        1.0, 0.0, trade_imbalance, trade_imbalance, 0.0, 0.0, 0.0, 0.0,
        close - 0.1, close + 0.1, 20.0, ts, ts + 1,
    )


def _harness() -> _RuleHarness:
    instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
    config = EvolutionStrategyConfig(
        instrument_id=instrument_id,
        bar_type=build_bar_type(instrument_id),
        state_data_type=DataType(EvolutionMarketState, metadata={"instrument_id": instrument_id}),
    )
    strategy = _RuleHarness(config)
    strategy._test_portfolio = _Portfolio()
    strategy.entries = []
    strategy.exits = 0
    return strategy


class EvolutionRuleStrategyTests(unittest.TestCase):
    def test_entry_requires_exact_consecutive_confirmations(self):
        strategy = _harness()
        strategy.on_data(_state(100.0))
        self.assertEqual(strategy.entries, [])
        strategy.on_data(_state(100.0, ts=2))
        self.assertEqual(strategy.entries, [100.0])

    def test_exit_all_and_any_modes(self):
        strategy = _harness()
        strategy.portfolio.flat = False
        strategy._rule_spec["exit"] = {
            "mode": "all",
            "conditions": strategy._rule_spec["exit"]["conditions"],
        }
        strategy.hold_bars = 2
        strategy.on_data(_state(98.0, trade_imbalance=1.0))
        self.assertEqual(strategy.exits, 0)
        strategy.on_data(_state(98.0, trade_imbalance=-1.0, ts=2))
        self.assertEqual(strategy.exits, 0)
        strategy.on_data(_state(98.0, trade_imbalance=-1.0, ts=3))
        self.assertEqual(strategy.exits, 1)

        strategy = _harness()
        strategy.portfolio.flat = False
        strategy._rule_spec["exit"] = {
            "mode": "any",
            "conditions": strategy._rule_spec["exit"]["conditions"],
        }
        strategy.hold_bars = 2
        strategy.on_data(_state(98.0))
        self.assertEqual(strategy.exits, 0)
        strategy.on_data(_state(98.0, ts=2))
        self.assertEqual(strategy.exits, 1)

    def test_min_hold_blocks_exit_and_cooldown_expires_on_flat_states(self):
        strategy = _harness()
        strategy.portfolio.flat = False
        strategy.on_data(_state(98.0))
        strategy.on_data(_state(98.0, trade_imbalance=-1.0, ts=2))
        self.assertEqual(strategy.exits, 0)
        self.assertEqual(strategy.hold_bars, 2)
        strategy.on_data(_state(98.0, trade_imbalance=-1.0, ts=3))
        self.assertEqual(strategy.exits, 1)
        self.assertEqual(strategy.cooldown_bars, 3)

        strategy.on_data(_state(100.0, ts=4))
        self.assertEqual(strategy.cooldown_bars, 2)
        strategy.on_data(_state(100.0, ts=5))
        self.assertEqual(strategy.cooldown_bars, 1)
        strategy.on_data(_state(100.0, ts=6))
        self.assertEqual(strategy.cooldown_bars, 0)
        self.assertEqual(strategy.entries, [100.0])

    def test_failed_confirmation_resets_counter(self):
        strategy = _harness()
        strategy.on_data(_state(100.0))
        self.assertEqual(strategy.entry_confirmations, 1)
        strategy.on_data(_state(99.0, ts=2))
        self.assertEqual(strategy.entry_confirmations, 0)
        strategy.on_data(_state(100.0, ts=3))
        strategy.on_data(_state(100.0, ts=4))
        self.assertEqual(strategy.entries, [100.0])

    def test_reset_clears_owned_state_and_rerun_is_equivalent(self):
        strategy = _harness()
        strategy.on_data(_state(100.0))
        strategy.cooldown_bars = 4
        strategy.exit_confirmations = 3
        strategy.hold_bars = 2
        strategy.on_reset()
        self.assertEqual(strategy.entry_confirmations, 0)
        self.assertEqual(strategy.exit_confirmations, 0)
        self.assertEqual(strategy.hold_bars, 0)
        self.assertEqual(strategy.cooldown_bars, 0)
        self.assertEqual(tuple(strategy.closes), ())

        first = _harness()
        first.on_data(_state(100.0))
        first.on_data(_state(100.0, ts=2))
        first.on_data(_state(98.0, trade_imbalance=-1.0, ts=3))
        first.on_data(_state(98.0, trade_imbalance=-1.0, ts=4))
        first.on_reset()
        first.portfolio.flat = True
        first.entries.clear()
        first.exits = 0
        for state in (_state(100.0), _state(100.0, ts=2)):
            first.on_data(state)
        second = _harness()
        for state in (_state(100.0), _state(100.0, ts=2)):
            second.on_data(state)
        self.assertEqual(first.entries, second.entries)
        self.assertEqual(first.exits, second.exits)
        self.assertEqual(first.entry_confirmations, second.entry_confirmations)

    def test_invalid_field_and_operator_fail_closed(self):
        base = dict(_RuleHarness.RULE_SPEC)
        invalid_field = dict(base, entry=[{"field": "not_a_state_field", "operator": "gt", "value": 1.0}])
        with self.assertRaisesRegex(ValueError, "invalid rule state field"):
            RuleInterpreterStrategy._validate_rule_spec(invalid_field)
        invalid_operator = dict(base, entry=[{"field": "close", "operator": "eq", "value": 1.0}])
        with self.assertRaisesRegex(ValueError, "invalid rule operator"):
            RuleInterpreterStrategy._validate_rule_spec(invalid_operator)


if __name__ == "__main__":
    unittest.main()
