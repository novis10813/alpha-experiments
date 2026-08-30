"""Parser and machine validator for declarative trading rules.

The validator deliberately accepts a small data language, not Python code.  Rule
sources are parsed as AST, checked to contain a literal dictionary assignment, and
only then evaluated with :func:`ast.literal_eval`.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import textwrap
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from evolution.rules.schema import Condition, EntryRule, ExitRule, RuleSpec


class RejectionCategory(StrEnum):
    SYNTAX = "syntax"
    STRUCTURE = "structure"
    SCHEMA = "schema"
    FAMILY = "family"
    FEATURE = "feature"
    ROLE = "role"
    BOUNDS = "bounds"
    THRESHOLD = "threshold"


@dataclass(frozen=True, slots=True)
class RuleValidationError:
    category: RejectionCategory
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class RuleValidationResult:
    valid: bool
    spec: RuleSpec | None
    errors: tuple[RuleValidationError, ...] = ()
    rejection_category: RejectionCategory | None = None
    canonical_json: str | None = None

    @property
    def rejection(self) -> RejectionCategory | None:
        """Compatibility-friendly name for the rejection category."""
        return self.rejection_category

    @property
    def category(self) -> RejectionCategory | None:
        return self.rejection_category


# These are intentionally local.  Importing evolution.families here would create a
# cycle once family integration starts consuming the rule validator.
TREND_FLOW_FEATURES = {
    "return_15m", "return_60m",
    "signed_flow_persistence_5m", "trade_imbalance", "volume_imbalance",
    "depth10_obi_mean", "depth10_obi_last", "obi_change_5m",
    "relative_spread_15m", "relative_volume_15m", "realized_volatility_15m",
}
TREND_FLOW_TREND = {"return_15m", "return_60m"}
TREND_FLOW_FLOW = {
    "signed_flow_persistence_5m", "trade_imbalance", "volume_imbalance",
}
TREND_FLOW_BOOK = {"depth10_obi_mean", "depth10_obi_last", "obi_change_5m"}

DOWN_STREAK_FEATURES = {
    "return_5m", "return_15m", "signed_flow_persistence_5m",
    "trade_imbalance", "volume_imbalance", "depth10_obi_mean",
    "depth10_obi_last", "relative_trade_density_15m", "relative_spread_15m",
}
DOWN_STREAK_DOWNSIDE = {
    "return_5m", "return_15m", "signed_flow_persistence_5m",
    "trade_imbalance", "volume_imbalance",
}

PULLBACK_FEATURES = {
    "return_15m", "return_60m", "return_5m", "close_location",
    "signed_flow_persistence_5m", "depth10_obi_mean", "depth10_obi_last",
    "obi_change_5m", "relative_spread_15m", "realized_volatility_15m",
    "relative_volume_15m",
}
PULLBACK_TREND = {"return_15m", "return_60m"}
PULLBACK_RECOVERY = {"return_5m", "close_location", "signed_flow_persistence_5m"}

FAMILY_FEATURES = {
    "trend-flow-confirmation-v1": TREND_FLOW_FEATURES,
    "down-streak-risk-off-btc-v1": DOWN_STREAK_FEATURES,
    "pullback-exhaustion-v1": PULLBACK_FEATURES,
}

# (lower bound, upper bound), inclusive.  The bound is applied to the literal
# threshold independently of the comparison operator.
THRESHOLD_BOUNDS = {
    "return_5m": (-0.10, 0.10),
    "return_15m": (-0.10, 0.10),
    "return_60m": (-0.10, 0.10),
    "signed_flow_persistence_5m": (-1.0, 1.0),
    "trade_imbalance": (-1.0, 1.0),
    "volume_imbalance": (-1.0, 1.0),
    "depth10_obi_mean": (-1.0, 1.0),
    "depth10_obi_last": (-1.0, 1.0),
    "obi_change_5m": (-1.0, 1.0),
    "close_location": (-1.0, 1.0),
    "relative_trade_density_15m": (0.0, 10.0),
    "relative_spread_15m": (0.0, 10.0),
    "relative_volume_15m": (0.0, 10.0),
    "spread_bps": (0.0, 10.0),
    "realized_volatility_15m": (0.0, 1.0),
}

_OPS = {"gt", "gte", "lt", "lte"}
_TOP_KEYS = {"family_id", "entry", "exit", "cooldown_bars"}
_ENTRY_KEYS = {"conditions", "confirmations"}
_EXIT_KEYS = {"conditions", "confirmations", "min_hold_bars"}
_EXIT_OPTIONAL_KEYS = {"mode"}
_CONDITION_KEYS = {"feature", "op", "value"}


def validate_rule_spec(value: object) -> RuleValidationResult:
    """Validate a dictionary and return an immutable typed result."""
    errors: list[RuleValidationError] = []
    if not isinstance(value, dict):
        return _result(None, [_error(RejectionCategory.SCHEMA, "$", "rule spec must be a dictionary")])

    _check_keys(value, _TOP_KEYS, "$", errors)
    family_id = value.get("family_id")
    if not isinstance(family_id, str) or not family_id:
        errors.append(_error(RejectionCategory.FAMILY, "$.family_id", "family_id must be a non-empty string"))
    elif family_id not in FAMILY_FEATURES:
        errors.append(_error(RejectionCategory.FAMILY, "$.family_id", f"unsupported family_id: {family_id}"))

    entry_value = value.get("entry")
    exit_value = value.get("exit")
    entry = _validate_entry(entry_value, errors)
    exit_rule = _validate_exit(exit_value, errors)
    cooldown = _validate_integer(value.get("cooldown_bars"), 0, 30, "$.cooldown_bars", errors)

    if entry is not None and family_id in FAMILY_FEATURES:
        _validate_features(entry.conditions, family_id, "$.entry.conditions", errors)
        _validate_entry_roles(entry.conditions, family_id, errors)
    if exit_rule is not None and family_id in FAMILY_FEATURES:
        _validate_features(exit_rule.conditions, family_id, "$.exit.conditions", errors)
        _validate_exit_roles(exit_rule.conditions, family_id, errors)

    if entry is None or exit_rule is None or not isinstance(family_id, str):
        return _result(None, errors or [_error(RejectionCategory.SCHEMA, "$", "invalid rule spec")])
    if errors:
        return _result(None, errors)
    spec = RuleSpec(family_id, entry, exit_rule, cooldown)
    return _result(spec, [])


def validate_rule_dict(value: object) -> RuleValidationResult:
    """Alias emphasizing that the input is the genotype dictionary."""
    return validate_rule_spec(value)


def validate_rule_source(source: str | Path) -> RuleValidationResult:
    """Extract and validate ``RULE_SPEC`` from a literal-only source block.

    A source may be a bare module assignment, a class containing that assignment,
    or a complete file with an ``EVOLVE-BLOCK``.  Only a direct module/class-body
    assignment is considered; calls, imports, expressions, and nested statements
    cannot pass the structural check.
    """
    if isinstance(source, Path):
        try:
            source = source.read_text(encoding="utf-8")
        except OSError as exc:
            return _result(None, [_error(RejectionCategory.SYNTAX, "$", str(exc))])
    if not isinstance(source, str):
        return _result(None, [_error(RejectionCategory.SYNTAX, "$", "source must be text")])

    block = _source_block(source)
    try:
        tree = ast.parse(textwrap.dedent(block))
    except SyntaxError as exc:
        return _result(None, [_error(RejectionCategory.SYNTAX, "$", f"syntax error: {exc.msg}")])

    assignments = _rule_assignments(tree)
    if len(assignments) != 1:
        return _result(None, [_error(
            RejectionCategory.STRUCTURE, "$",
            "source must contain exactly one direct RULE_SPEC assignment",
        )])
    assignment = assignments[0]
    if len(assignment.targets) != 1 or not isinstance(assignment.targets[0], ast.Name) or assignment.targets[0].id != "RULE_SPEC":
        return _result(None, [_error(
            RejectionCategory.STRUCTURE, "RULE_SPEC", "RULE_SPEC must be one simple assignment",
        )])
    if not _is_literal_node(assignment.value):
        return _result(None, [_error(
            RejectionCategory.STRUCTURE, "RULE_SPEC", "RULE_SPEC must be a literal dictionary",
        )])
    if not isinstance(assignment.value, ast.Dict):
        return _result(None, [_error(
            RejectionCategory.SCHEMA, "RULE_SPEC", "RULE_SPEC must evaluate to a dictionary",
        )])
    try:
        value = ast.literal_eval(assignment.value)
    except (ValueError, TypeError, MemoryError, RecursionError) as exc:
        return _result(None, [_error(RejectionCategory.STRUCTURE, "RULE_SPEC", f"invalid literal: {exc}")])
    return validate_rule_spec(value)


def parse_rule_source(source: str | Path) -> RuleValidationResult:
    """Public spelling for source parsing and validation."""
    return validate_rule_source(source)


def parse_rule_spec(source: str | Path) -> RuleValidationResult:
    """Alias for callers treating a source as a serialized rule spec."""
    return validate_rule_source(source)


def canonical_rule_json(spec: RuleSpec | dict[str, object]) -> str:
    """Return deterministic normalized JSON suitable for source signatures."""
    if isinstance(spec, RuleSpec):
        payload: dict[str, object] = {
            "family_id": spec.family_id,
            "entry": {
                "conditions": [_condition_dict(item) for item in spec.entry.conditions],
                "confirmations": spec.entry.confirmations,
            },
            "exit": {
                "conditions": [_condition_dict(item) for item in spec.exit.conditions],
                "confirmations": spec.exit.confirmations,
                "min_hold_bars": spec.exit.min_hold_bars,
                "mode": spec.exit.mode,
            },
            "cooldown_bars": spec.cooldown_bars,
        }
    else:
        result = validate_rule_spec(spec)
        if not result.valid or result.spec is None:
            raise ValueError("cannot canonicalize an invalid rule spec")
        return canonical_rule_json(result.spec)
    payload["entry"]["conditions"] = sorted(  # type: ignore[index]
        payload["entry"]["conditions"],  # type: ignore[index]
        key=lambda item: (str(item["feature"]), str(item["op"]), item["value"]),  # type: ignore[index]
    )
    payload["exit"]["conditions"] = sorted(  # type: ignore[index]
        payload["exit"]["conditions"],  # type: ignore[index]
        key=lambda item: (str(item["feature"]), str(item["op"]), item["value"]),  # type: ignore[index]
    )
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def rule_source_signature(source: str | Path | RuleSpec | dict[str, object]) -> str:
    """Hash the normalized rule JSON, making formatting/key order irrelevant."""
    if isinstance(source, RuleSpec):
        canonical = canonical_rule_json(source)
    elif isinstance(source, dict):
        canonical = canonical_rule_json(source)
    else:
        result = validate_rule_source(source)
        if not result.valid or result.canonical_json is None:
            raise ValueError("cannot sign an invalid rule source")
        canonical = result.canonical_json
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_entry(value: object, errors: list[RuleValidationError]) -> EntryRule | None:
    if not isinstance(value, dict):
        errors.append(_error(RejectionCategory.SCHEMA, "$.entry", "entry must be a dictionary"))
        return None
    _check_keys(value, _ENTRY_KEYS, "$.entry", errors)
    conditions = _validate_conditions(value.get("conditions"), "$.entry.conditions", errors)
    confirmations = _validate_integer(value.get("confirmations"), 1, 5, "$.entry.confirmations", errors)
    if conditions is None or confirmations is None:
        return None
    return EntryRule(conditions, confirmations)


def _validate_exit(value: object, errors: list[RuleValidationError]) -> ExitRule | None:
    if not isinstance(value, dict):
        errors.append(_error(RejectionCategory.SCHEMA, "$.exit", "exit must be a dictionary"))
        return None
    _check_keys(value, _EXIT_KEYS, "$.exit", errors, _EXIT_OPTIONAL_KEYS)
    conditions = _validate_conditions(value.get("conditions"), "$.exit.conditions", errors)
    confirmations = _validate_integer(value.get("confirmations"), 1, 5, "$.exit.confirmations", errors)
    min_hold = _validate_integer(value.get("min_hold_bars"), 1, 60, "$.exit.min_hold_bars", errors)
    mode = value.get("mode", "all")
    if mode not in {"all", "any"}:
        errors.append(_error(RejectionCategory.SCHEMA, "$.exit.mode", "mode must be 'all' or 'any'"))
        mode = None
    if conditions is None or confirmations is None or min_hold is None or mode is None:
        return None
    return ExitRule(conditions, confirmations, min_hold, mode)


def _validate_conditions(value: object, path: str, errors: list[RuleValidationError]) -> tuple[Condition, ...] | None:
    if not isinstance(value, list):
        errors.append(_error(RejectionCategory.SCHEMA, path, "conditions must be a flat list"))
        return None
    if not 1 <= len(value) <= 4:
        errors.append(_error(RejectionCategory.BOUNDS, path, "conditions must contain 1 to 4 items"))
    parsed: list[Condition] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict) or set(item) != _CONDITION_KEYS:
            errors.append(_error(RejectionCategory.SCHEMA, item_path, "condition must have exactly feature, op, and value"))
            continue
        feature = item["feature"]
        op = item["op"]
        number = item["value"]
        if not isinstance(feature, str) or not feature:
            errors.append(_error(RejectionCategory.SCHEMA, f"{item_path}.feature", "feature must be a string"))
        if op not in _OPS:
            errors.append(_error(RejectionCategory.SCHEMA, f"{item_path}.op", "op must be gt, gte, lt, or lte"))
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            errors.append(_error(RejectionCategory.THRESHOLD, f"{item_path}.value", "value must be an int or float, not bool"))
        elif not _is_finite(number):
            errors.append(_error(RejectionCategory.THRESHOLD, f"{item_path}.value", "value must be finite"))
        if isinstance(feature, str) and feature and op in _OPS and isinstance(number, (int, float)) and not isinstance(number, bool) and _is_finite(number):
            parsed.append(Condition(feature, op, number))
    return tuple(parsed) if len(parsed) == len(value) and 1 <= len(parsed) <= 4 else None


def _validate_integer(value: object, lower: int, upper: int, path: str, errors: list[RuleValidationError]) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(_error(RejectionCategory.BOUNDS, path, f"value must be an integer from {lower} to {upper}"))
        return None
    if not lower <= value <= upper:
        errors.append(_error(RejectionCategory.BOUNDS, path, f"value must be from {lower} to {upper}"))
        return None
    return value


def _validate_features(conditions: tuple[Condition, ...], family_id: str, path: str, errors: list[RuleValidationError]) -> None:
    allowed = FAMILY_FEATURES[family_id]
    for index, condition in enumerate(conditions):
        if condition.feature not in allowed:
            errors.append(_error(RejectionCategory.FEATURE, f"{path}[{index}].feature", f"feature is not allowed for {family_id}: {condition.feature}"))
        bounds = THRESHOLD_BOUNDS.get(condition.feature)
        if bounds is not None and not bounds[0] <= condition.value <= bounds[1]:
            errors.append(_error(RejectionCategory.THRESHOLD, f"{path}[{index}].value", f"threshold must be between {bounds[0]} and {bounds[1]} for {condition.feature}"))


def _validate_entry_roles(conditions: tuple[Condition, ...], family_id: str, errors: list[RuleValidationError]) -> None:
    features = {condition.feature for condition in conditions}
    if family_id == "trend-flow-confirmation-v1":
        for role, required in (("trend", TREND_FLOW_TREND), ("flow", TREND_FLOW_FLOW), ("book", TREND_FLOW_BOOK)):
            if not features & required:
                errors.append(_error(RejectionCategory.ROLE, "$.entry.conditions", f"entry must include a {role} feature"))
    elif family_id == "pullback-exhaustion-v1":
        for role, required in (("broad-trend", PULLBACK_TREND), ("pullback/recovery", PULLBACK_RECOVERY)):
            if not features & required:
                errors.append(_error(RejectionCategory.ROLE, "$.entry.conditions", f"entry must include a {role} feature"))


def _validate_exit_roles(conditions: tuple[Condition, ...], family_id: str, errors: list[RuleValidationError]) -> None:
    if family_id == "down-streak-risk-off-btc-v1" and not ({condition.feature for condition in conditions} & DOWN_STREAK_DOWNSIDE):
        errors.append(_error(RejectionCategory.ROLE, "$.exit.conditions", "exit must include a downside pressure feature"))


def _check_keys(
    value: dict[object, object],
    expected: set[str],
    path: str,
    errors: list[RuleValidationError],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = expected - set(value)
    extra = set(value) - expected - optional
    if missing:
        errors.append(_error(RejectionCategory.SCHEMA, path, f"missing keys: {', '.join(sorted(map(str, missing)))}"))
    if extra:
        errors.append(_error(RejectionCategory.SCHEMA, path, f"unknown keys: {', '.join(sorted(map(str, extra)))}"))


def _rule_assignments(tree: ast.Module) -> list[ast.Assign]:
    """Return the only allowed direct assignment form, if structurally isolated."""
    if len(tree.body) == 1 and isinstance(tree.body[0], ast.Assign):
        return [tree.body[0]]
    if len(tree.body) == 1 and isinstance(tree.body[0], ast.ClassDef):
        class_body = tree.body[0].body
        if len(class_body) == 1 and isinstance(class_body[0], ast.Assign):
            return [class_body[0]]
    return []


def _is_finite(value: int | float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _is_literal_node(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, int, float, bool, type(None)))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, (int, float)) and not isinstance(node.operand.value, bool)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_literal_node(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(key is not None and _is_literal_node(key) and _is_literal_node(value) for key, value in zip(node.keys, node.values, strict=True))
    return False


def _source_block(source: str) -> str:
    start = "# EVOLVE-BLOCK-START"
    end = "# EVOLVE-BLOCK-END"
    if source.count(start) == 1 and source.count(end) == 1:
        return source.split(start, 1)[1].split(end, 1)[0]
    return source


def _condition_dict(condition: Condition) -> dict[str, object]:
    # JSON distinguishes 0 from 0.0 even though both are the same threshold.
    # Normalize integral values (including negative zero) before signing.
    value = condition.value
    normalized = int(value) if float(value).is_integer() else float(value)
    return {"feature": condition.feature, "op": condition.op, "value": normalized}


def _error(category: RejectionCategory, path: str, message: str) -> RuleValidationError:
    return RuleValidationError(category, path, message)


def _result(spec: RuleSpec | None, errors: list[RuleValidationError]) -> RuleValidationResult:
    frozen_errors = tuple(errors)
    category = frozen_errors[0].category if frozen_errors else None
    canonical = canonical_rule_json(spec) if spec is not None else None
    return RuleValidationResult(spec is not None and not frozen_errors, spec, frozen_errors, category, canonical)


# Short aliases keep the API convenient while the descriptive names remain canonical.
ValidationError = RuleValidationError
ValidationResult = RuleValidationResult
RuleSpecValidationError = RuleValidationError
canonical_json = canonical_rule_json
source_signature = rule_source_signature
