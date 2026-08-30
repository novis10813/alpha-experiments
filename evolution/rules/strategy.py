"""Runtime for validated declarative evolution rules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from decimal import Decimal
from math import isfinite
from numbers import Real
from typing import Any, ClassVar, Protocol

from evolution.market_state import EvolutionMarketState
from evolution.strategy_base import EvolutionStrategyBase, EvolutionStrategyConfig
from evolution.rules.validator import validate_rule_dict
from nautilus_trader.model.data import CustomData


class EvolutionStateFieldReader(Protocol):
    """Narrow adapter for reading a validated scalar state field."""

    def __call__(self, state: EvolutionMarketState, field: str) -> Real | Decimal: ...


_RULE_FIELDS = frozenset(EvolutionMarketState.FIELDS) - {"instrument_id", "ts_event", "ts_init"}
_ALLOWED_OPERATORS = frozenset({"gt", "gte", "lt", "lte"})
_ALLOWED_EXIT_MODES = frozenset({"all", "any"})


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (Real, Decimal))
        and isfinite(value)
    )


def read_state_scalar(state: EvolutionMarketState, field: str) -> Real:
    """Read one direct finite numeric market-state field."""
    if field not in _RULE_FIELDS:
        raise ValueError(f"invalid rule feature: {field!r}")
    value = getattr(state, field, None)
    if not _finite_number(value):
        raise ValueError(f"rule feature {field!r} must be finite numeric")
    return value


class RuleInterpreterStrategy(EvolutionStrategyBase):
    """Fixed long/flat runtime for a schema-v2 ``RULE_SPEC`` mapping."""

    RULE_SPEC: ClassVar[Mapping[str, Any]] = {}
    state_field_reader: ClassVar[EvolutionStateFieldReader] = staticmethod(read_state_scalar)

    @classmethod
    def _validate_rule_spec(cls, raw: Mapping[str, Any]) -> dict[str, Any]:
        result = validate_rule_dict(raw)
        if not result.valid or result.spec is None:
            message = "; ".join(error.message for error in result.errors)
            raise ValueError(f"invalid RULE_SPEC: {message or 'validation failed'}")
        return asdict(result.spec)

    def __init__(self, config: EvolutionStrategyConfig) -> None:
        super().__init__(config)
        self._rule_spec = self._validate_rule_spec(self.RULE_SPEC)
        self.entry_confirmations = 0
        self.exit_confirmations = 0
        self.hold_bars = 0
        self.cooldown_bars = 0

    def on_data(self, data: CustomData) -> None:
        state = data.data if isinstance(data, CustomData) else data
        if not isinstance(state, EvolutionMarketState) and not hasattr(state, "close"):
            raise ValueError("rule runtime requires EvolutionMarketState data")
        if self.portfolio is None:
            raise RuntimeError("rule runtime requires an attached portfolio")

        if self.portfolio.is_flat(self.config.instrument_id):
            self.hold_bars = 0
            self.exit_confirmations = 0
            self.cooldown_bars = max(0, self.cooldown_bars - 1)
            matched = self._matches(self._rule_spec["entry"]["conditions"], "all", state)
            self.entry_confirmations = self.entry_confirmations + 1 if matched else 0
            if self.cooldown_bars == 0 and self.entry_confirmations >= self._rule_spec["entry"]["confirmations"]:
                self.enter_long(state.close)
                self.entry_confirmations = 0
            return

        self.hold_bars += 1
        self.entry_confirmations = 0
        if self.hold_bars < self._rule_spec["exit"]["min_hold_bars"]:
            self.exit_confirmations = 0
            return
        matched = self._matches(
            self._rule_spec["exit"]["conditions"],
            self._rule_spec["exit"]["mode"],
            state,
        )
        self.exit_confirmations = self.exit_confirmations + 1 if matched else 0
        if self.exit_confirmations >= self._rule_spec["exit"]["confirmations"]:
            self.exit_long()
            self.exit_confirmations = 0
            self.cooldown_bars = self._rule_spec["cooldown_bars"]

    def on_reset(self) -> None:
        try:
            super().on_reset()
        except AttributeError:
            if hasattr(self, "closes"):
                self.closes.clear()
        self.entry_confirmations = 0
        self.exit_confirmations = 0
        self.hold_bars = 0
        self.cooldown_bars = 0

    def _matches(self, conditions, mode: str, state: EvolutionMarketState) -> bool:
        if mode not in _ALLOWED_EXIT_MODES:
            raise ValueError(f"invalid rule exit mode: {mode!r}")
        results = [self._matches_condition(condition, state) for condition in conditions]
        return all(results) if mode == "all" else any(results)

    def _matches_condition(self, condition, state: EvolutionMarketState) -> bool:
        if not isinstance(condition, Mapping):
            raise ValueError("rule condition must be a mapping")
        feature = condition.get("feature")
        op = condition.get("op")
        threshold = condition.get("value")
        if feature not in _RULE_FIELDS:
            raise ValueError(f"invalid rule feature: {feature!r}")
        if op not in _ALLOWED_OPERATORS:
            raise ValueError(f"invalid rule operator: {op!r}")
        if not _finite_number(threshold):
            raise ValueError(f"rule threshold for {feature!r} must be finite numeric")
        value = type(self).state_field_reader(state, feature)
        if not _finite_number(value):
            raise ValueError(f"rule feature {feature!r} must be finite numeric")
        value = float(value)
        threshold = float(threshold)
        if op == "gt":
            return value > threshold
        if op == "gte":
            return value >= threshold
        if op == "lt":
            return value < threshold
        if op == "lte":
            return value <= threshold
        raise ValueError(f"invalid rule operator: {op!r}")
