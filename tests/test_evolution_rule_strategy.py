from __future__ import annotations

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
        "family_id": "trend-flow-confirmation-v1",
        "entry": {"conditions": [
            {"feature": "return_15m", "op": "gte", "value": 0.0},
            {"feature": "signed_flow_persistence_5m", "op": "gte", "value": -1.0},
            {"feature": "depth10_obi_mean", "op": "gte", "value": -1.0},
        ], "confirmations": 2},
        "exit": {"mode": "all", "conditions": [
            {"feature": "return_15m", "op": "lt", "value": 0.0},
            {"feature": "signed_flow_persistence_5m", "op": "lt", "value": 0.0},
        ], "confirmations": 2, "min_hold_bars": 2},
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


def _state(return_15m: float, flow: float = 1.0, close: float = 100.0, ts: int = 1) -> EvolutionMarketState:
    return EvolutionMarketState(
        "BTCUSDT.BINANCE", close, close, close, close, 1.0, 1, 1, 0,
        1.0, 0.0, flow, flow, 0.1, 0.1, 0.0, 0.0,
        close - 0.1, close + 0.1, 20.0, ts, ts + 1,
        return_15m=return_15m, signed_flow_persistence_5m=flow,
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
        strategy.on_data(_state(0.0))
        self.assertEqual(strategy.entries, [])
        strategy.on_data(_state(0.0, ts=2))
        self.assertEqual(strategy.entries, [100.0])

    def test_exit_all_and_any_modes(self):
        strategy = _harness()
        strategy.portfolio.flat = False
        strategy._rule_spec["exit"]["mode"] = "all"
        strategy.hold_bars = 2
        strategy.on_data(_state(-1.0, flow=1.0))
        strategy.on_data(_state(-1.0, flow=-1.0, ts=2))
        self.assertEqual(strategy.exits, 0)
        strategy.on_data(_state(-1.0, flow=-1.0, ts=3))
        self.assertEqual(strategy.exits, 1)

        strategy = _harness()
        strategy.portfolio.flat = False
        strategy._rule_spec["exit"]["mode"] = "any"
        strategy.hold_bars = 2
        strategy.on_data(_state(-1.0, flow=1.0))
        strategy.on_data(_state(-1.0, flow=1.0, ts=2))
        self.assertEqual(strategy.exits, 1)

    def test_min_hold_blocks_exit_and_cooldown_expires_on_flat_states(self):
        strategy = _harness()
        strategy.portfolio.flat = False
        strategy.on_data(_state(-1.0, flow=-1.0))
        strategy.on_data(_state(-1.0, flow=-1.0, ts=2))
        self.assertEqual(strategy.exits, 0)
        self.assertEqual(strategy.hold_bars, 2)
        strategy.on_data(_state(-1.0, flow=-1.0, ts=3))
        self.assertEqual(strategy.exits, 1)
        self.assertEqual(strategy.cooldown_bars, 3)

        strategy.on_data(_state(0.0, ts=4))
        strategy.on_data(_state(0.0, ts=5))
        strategy.on_data(_state(0.0, ts=6))
        self.assertEqual(strategy.cooldown_bars, 0)
        self.assertEqual(strategy.entries, [100.0])

    def test_failed_confirmation_resets_counter(self):
        strategy = _harness()
        strategy.on_data(_state(0.0))
        self.assertEqual(strategy.entry_confirmations, 1)
        strategy.on_data(_state(-1.0, ts=2))
        self.assertEqual(strategy.entry_confirmations, 0)
        strategy.on_data(_state(0.0, ts=3))
        strategy.on_data(_state(0.0, ts=4))
        self.assertEqual(strategy.entries, [100.0])

    def test_reset_clears_owned_state_and_rerun_is_equivalent(self):
        strategy = _harness()
        strategy.on_data(_state(0.0))
        strategy.cooldown_bars = 4
        strategy.exit_confirmations = 3
        strategy.hold_bars = 2
        strategy.on_reset()
        self.assertEqual(strategy.entry_confirmations, 0)
        self.assertEqual(strategy.exit_confirmations, 0)
        self.assertEqual(strategy.hold_bars, 0)
        self.assertEqual(strategy.cooldown_bars, 0)

    def test_invalid_field_and_operator_fail_closed(self):
        base = dict(_RuleHarness.RULE_SPEC)
        invalid_field = dict(base, entry={"conditions": [{"feature": "not_a_state_field", "op": "gt", "value": 1.0}], "confirmations": 1})
        with self.assertRaisesRegex(ValueError, "invalid rule state field|not allowed"):
            RuleInterpreterStrategy._validate_rule_spec(invalid_field)
        invalid_operator = dict(base, entry={"conditions": [{"feature": "return_15m", "op": "eq", "value": 1.0}], "confirmations": 1})
        with self.assertRaisesRegex(ValueError, "invalid rule operator|gt, gte"):
            RuleInterpreterStrategy._validate_rule_spec(invalid_operator)


if __name__ == "__main__":
    unittest.main()
