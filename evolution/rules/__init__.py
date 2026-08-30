"""Declarative rule schema, validation, and runtime."""

from .schema import Condition, EntryRule, ExitRule, RuleSpec
from .strategy import EvolutionStateFieldReader, RuleInterpreterStrategy, read_state_scalar
from .validator import (
    RejectionCategory,
    RuleValidationError,
    RuleValidationResult,
    canonical_rule_json,
    parse_rule_source,
    parse_rule_spec,
    rule_source_signature,
    validate_rule_dict,
    validate_rule_source,
    validate_rule_spec,
)

__all__ = [
    "Condition",
    "EntryRule",
    "ExitRule",
    "EvolutionStateFieldReader",
    "RejectionCategory",
    "RuleInterpreterStrategy",
    "RuleSpec",
    "RuleValidationError",
    "RuleValidationResult",
    "canonical_rule_json",
    "parse_rule_source",
    "parse_rule_spec",
    "read_state_scalar",
    "rule_source_signature",
    "validate_rule_dict",
    "validate_rule_source",
    "validate_rule_spec",
]
