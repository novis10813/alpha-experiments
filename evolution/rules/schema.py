"""Immutable data types for declarative evolution rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


Numeric: TypeAlias = int | float


@dataclass(frozen=True, slots=True)
class Condition:
    feature: str
    op: str
    value: Numeric


@dataclass(frozen=True, slots=True)
class EntryRule:
    conditions: tuple[Condition, ...]
    confirmations: int


@dataclass(frozen=True, slots=True)
class ExitRule:
    conditions: tuple[Condition, ...]
    confirmations: int
    min_hold_bars: int
    mode: str = "all"


@dataclass(frozen=True, slots=True)
class RuleSpec:
    family_id: str
    entry: EntryRule
    exit: ExitRule
    cooldown_bars: int


__all__ = [
    "Condition",
    "EntryRule",
    "ExitRule",
    "Numeric",
    "RuleSpec",
]
