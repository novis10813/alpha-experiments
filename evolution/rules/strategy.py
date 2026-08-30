from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from math import isfinite
from numbers import Real
from typing import Any
from typing import ClassVar
from typing import Protocol

from evolution.initial_program import EvolvedStrategy as FixedEvolutionStrategy
from evolution.initial_program import EvolutionStrategyConfig
from evolution.market_state import EvolutionMarketState
from nautilus_trader.model.data import CustomData


class EvolutionStateFieldReader(Protocol):
    """Narrow adapter for reading a validated scalar state field."""

    def __call__(self, state: EvolutionMarketState, field: str) -> Real | Decimal: ...


_ALLOWED_OPERATORS = frozenset({"gt", "gte", "lt", "lte"})
_ALLOWED_EXIT_MODES = frozenset({"all", "any"})
_RULE_FIELDS = frozenset(EvolutionMarketState.FIELDS) - {"instrument_id", "ts_event", "ts_init"}


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (Real, Decimal))
        and isfinite(value)
    )


def read_state_scalar(state: EvolutionMarketState, field: str) -> Real:
    """Read one direct finite numeric market-state field."""
    if field not in _RULE_FIELDS:
        raise ValueError(f"invalid rule state field: {field!r}")
    value = getattr(state, field, None)
    if not _finite_number(value):
        raise ValueError(f"rule state field {field!r} must be finite numeric")
    return value


class RuleInterpreterStrategy(FixedEvolutionStrategy):
    """Fixed long/flat runtime for a validated declarative ``RULE_SPEC``.

    The expected plain mapping shape is::

        {
            "entry": [{"field": "close", "operator": "gt", "value": 100.0}],
            "entry_confirmations": 2,
            "exit": {
                "mode": "all",
                "conditions": [{"field": "close", "operator": "lt", "value": 99.0}],
            },
            "exit_confirmations": 2,
            "min_hold_bars": 5,
            "cooldown_bars": 3,
        }

    ``entry`` is always a flat AND. Exit conditions are combined by ``mode``.
    """

    RULE_SPEC: ClassVar[Mapping[str, Any]] = {}
    state_field_reader: ClassVar[EvolutionStateFieldReader] = staticmethod(read_state_scalar)

    def __init__(self, config: EvolutionStrategyConfig) -> None:
        super().__init__(config)
        self.entry_confirmations = 0
        self.exit_confirmations = 0
        self.hold_bars = 0
        self.cooldown_bars = 0
        self._rule_spec = self._validate_rule_spec(self.RULE_SPEC)

    def on_data(self, data: CustomData) -> None:
        state = data.data if isinstance(data, CustomData) else data
        if not isinstance(state, EvolutionMarketState):
            raise ValueError("rule runtime requires EvolutionMarketState data")

        if self.portfolio is None:
            raise RuntimeError("rule runtime requires an attached portfolio")
        if self.portfolio.is_flat(self.config.instrument_id):
            self.hold_bars = 0
            self.exit_confirmations = 0
            # A completed state is one call to on_data. Cooldown ticks only
            # while flat, before evaluating the current entry state.
            self.cooldown_bars = max(0, self.cooldown_bars - 1)
            entry_state = self._matches(self._rule_spec["entry"], "all", state)
            self.entry_confirmations = self.entry_confirmations + 1 if entry_state else 0
            if self.cooldown_bars == 0 and self.entry_confirmations >= self._rule_spec["entry_confirmations"]:
                self.enter_long(state.close)
                self.entry_confirmations = 0
            return

        self.hold_bars += 1
        self.entry_confirmations = 0
        if self.hold_bars < self._rule_spec["min_hold_bars"]:
            self.exit_confirmations = 0
            return

        exit_spec = self._rule_spec["exit"]
        exit_state = self._matches(exit_spec["conditions"], exit_spec["mode"], state)
        self.exit_confirmations = self.exit_confirmations + 1 if exit_state else 0
        if self.exit_confirmations >= self._rule_spec["exit_confirmations"]:
            self.exit_long()
            self.exit_confirmations = 0
            self.cooldown_bars = self._rule_spec["cooldown_bars"]

    def on_reset(self) -> None:
        # The fixed superclass clears its own execution state/history. The
        # interpreter then clears every counter it owns.
        super().on_reset()
        self.entry_confirmations = 0
        self.exit_confirmations = 0
        self.hold_bars = 0
        self.cooldown_bars = 0

    def _matches(
        self,
        conditions: list[Mapping[str, Any]],
        mode: str,
        state: EvolutionMarketState,
    ) -> bool:
        if mode not in _ALLOWED_EXIT_MODES:
            raise ValueError(f"invalid rule exit mode: {mode!r}")
        results = [self._matches_condition(condition, state) for condition in conditions]
        return all(results) if mode == "all" else any(results)

    def _matches_condition(self, condition: Mapping[str, Any], state: EvolutionMarketState) -> bool:
        field = condition["field"]
        operator = condition["operator"]
        threshold = condition["value"]
        if field not in _RULE_FIELDS:
            raise ValueError(f"invalid rule state field: {field!r}")
        if operator not in _ALLOWED_OPERATORS:
            raise ValueError(f"invalid rule operator: {operator!r}")
        if not _finite_number(threshold):
            raise ValueError(f"rule threshold for {field!r} must be finite numeric")
        value = type(self).state_field_reader(state, field)
        if not _finite_number(value):
            raise ValueError(f"rule state field {field!r} must be finite numeric")
        value = float(value)
        threshold = float(threshold)
        if operator == "gt":
            return value > threshold
        if operator == "gte":
            return value >= threshold
        if operator == "lt":
            return value < threshold
        if operator == "lte":
            return value <= threshold
        # This is unreachable after validation, but keeps an adapted or
        # mutated unvalidated spec from taking an action.
        raise ValueError(f"invalid rule operator: {operator!r}")

    @classmethod
    def _validate_rule_spec(cls, raw: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            raise ValueError("RULE_SPEC must be a mapping")
        if not raw:
            raise ValueError("RULE_SPEC must define a rule")
        required = ("entry", "exit", "min_hold_bars", "cooldown_bars")
        missing = [key for key in required if key not in raw]
        if missing:
            raise ValueError(f"RULE_SPEC missing key: {missing[0]!r}")

        entry_spec = raw["entry"]
        entry_confirmations = raw.get("entry_confirmations")
        if isinstance(entry_spec, Mapping):
            entry_confirmations = entry_spec.get("confirmations", entry_confirmations)
            entry_spec = entry_spec.get("conditions")
        entry_conditions = cls._validate_conditions(entry_spec, "entry")
        exit_spec = raw["exit"]
        if not isinstance(exit_spec, Mapping):
            raise ValueError("RULE_SPEC exit must be a mapping")
        mode = exit_spec.get("mode")
        if mode not in _ALLOWED_EXIT_MODES:
            raise ValueError("RULE_SPEC exit mode must be 'all' or 'any'")
        exit_conditions = cls._validate_conditions(exit_spec.get("conditions"), "exit")
        exit_confirmations = raw.get("exit_confirmations", exit_spec.get("confirmations"))

        return {
            "entry": entry_conditions,
            "entry_confirmations": cls._positive_int(entry_confirmations, "entry_confirmations"),
            "exit": {"mode": mode, "conditions": exit_conditions},
            "exit_confirmations": cls._positive_int(exit_confirmations, "exit_confirmations"),
            "min_hold_bars": cls._nonnegative_int(raw["min_hold_bars"], "min_hold_bars"),
            "cooldown_bars": cls._nonnegative_int(raw["cooldown_bars"], "cooldown_bars"),
        }

    @classmethod
    def _validate_conditions(cls, conditions: Any, name: str) -> list[dict[str, Any]]:
        if not isinstance(conditions, (list, tuple)) or not conditions:
            raise ValueError(f"RULE_SPEC {name} conditions must be non-empty")
        validated = []
        for condition in conditions:
            if not isinstance(condition, Mapping):
                raise ValueError(f"RULE_SPEC {name} condition must be a mapping")
            field = condition.get("field")
            operator = condition.get("operator")
            value = condition.get("value")
            if not isinstance(field, str) or field not in _RULE_FIELDS:
                raise ValueError(f"invalid rule state field: {field!r}")
            if operator not in _ALLOWED_OPERATORS:
                raise ValueError(f"invalid rule operator: {operator!r}")
            if not _finite_number(value):
                raise ValueError(f"rule threshold for {field!r} must be finite numeric")
            validated.append({"field": field, "operator": operator, "value": value})
        return validated

    @staticmethod
    def _positive_int(value: Any, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
        return value

    @staticmethod
    def _nonnegative_int(value: Any, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
        return value
