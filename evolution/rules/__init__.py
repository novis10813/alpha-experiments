"""Declarative rule schema and validation."""

from .schema import Condition, EntryRule, ExitRule, RuleSpec
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
    "RejectionCategory",
    "RuleSpec",
    "RuleValidationError",
    "RuleValidationResult",
    "canonical_rule_json",
    "parse_rule_source",
    "parse_rule_spec",
    "rule_source_signature",
    "validate_rule_dict",
    "validate_rule_source",
    "validate_rule_spec",
]
