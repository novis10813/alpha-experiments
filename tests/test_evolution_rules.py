import json
import math
import unittest

from evolution.rules import RejectionCategory
from evolution.rules import canonical_rule_json
from evolution.rules import rule_source_signature
from evolution.rules import validate_rule_dict
from evolution.rules import validate_rule_source


class EvolutionRuleSchemaTests(unittest.TestCase):
    def test_valid_family_specs_return_immutable_typed_specs(self):
        for family_id, conditions, exit_conditions in (
            (
                "trend-flow-confirmation-v1",
                [
                    {"feature": "return_15m", "op": "gt", "value": 0.01},
                    {"feature": "trade_imbalance", "op": "gte", "value": 0},
                    {"feature": "depth10_obi_mean", "op": "gt", "value": 0.1},
                ],
                [{"feature": "return_15m", "op": "lt", "value": -0.02}],
            ),
            (
                "down-streak-risk-off-btc-v1",
                [{"feature": "relative_spread_15m", "op": "lte", "value": 2}],
                [{"feature": "return_5m", "op": "lt", "value": -0.02}],
            ),
            (
                "pullback-exhaustion-v1",
                [
                    {"feature": "return_60m", "op": "gt", "value": 0.01},
                    {"feature": "close_location", "op": "gte", "value": 0},
                ],
                [{"feature": "depth10_obi_last", "op": "lt", "value": -0.3}],
            ),
        ):
            result = validate_rule_dict({
                "family_id": family_id,
                "entry": {"conditions": conditions, "confirmations": 2},
                "exit": {
                    "conditions": exit_conditions,
                    "confirmations": 1,
                    "min_hold_bars": 3,
                },
                "cooldown_bars": 4,
            })
            self.assertTrue(result.valid, result.errors)
            self.assertEqual(result.spec.family_id, family_id)
            self.assertIsInstance(result.spec.entry.conditions, tuple)
            self.assertEqual(result.spec.exit.mode, "all")
            with self.assertRaises(AttributeError):
                result.spec.cooldown_bars = 2

    def test_required_roles_are_machine_enforced(self):
        base = {
            "family_id": "trend-flow-confirmation-v1",
            "entry": {"conditions": [
                {"feature": "return_15m", "op": "gt", "value": 0},
            ], "confirmations": 1},
            "exit": {"conditions": [
                {"feature": "return_15m", "op": "lt", "value": 0},
            ], "confirmations": 1, "min_hold_bars": 1},
            "cooldown_bars": 0,
        }
        result = validate_rule_dict(base)
        self.assertFalse(result.valid)
        self.assertEqual(result.rejection_category, RejectionCategory.ROLE)
        self.assertGreaterEqual(sum(error.category == RejectionCategory.ROLE for error in result.errors), 2)

        down = {
            "family_id": "down-streak-risk-off-btc-v1",
            "entry": {"conditions": [{"feature": "return_5m", "op": "lt", "value": 0}], "confirmations": 1},
            "exit": {"conditions": [{"feature": "depth10_obi_last", "op": "lt", "value": 0}], "confirmations": 1, "min_hold_bars": 1},
            "cooldown_bars": 0,
        }
        result = validate_rule_dict(down)
        self.assertFalse(result.valid)
        self.assertTrue(any(error.category == RejectionCategory.ROLE for error in result.errors))

    def test_disallowed_feature_and_nested_logic_are_rejected(self):
        spec = {
            "family_id": "trend-flow-confirmation-v1",
            "entry": {"conditions": [
                {"feature": "close", "op": "gt", "value": 1},
                {"feature": "trade_imbalance", "op": "gt", "value": 0},
                {"feature": "depth10_obi_mean", "op": "gt", "value": 0},
            ], "confirmations": 1},
            "exit": {"conditions": [{"feature": "return_15m", "op": "lt", "value": 0}], "confirmations": 1, "min_hold_bars": 1},
            "cooldown_bars": 0,
        }
        result = validate_rule_dict(spec)
        self.assertFalse(result.valid)
        self.assertTrue(any(error.category == RejectionCategory.FEATURE for error in result.errors))

        source = "RULE_SPEC = {'family_id': 'trend-flow-confirmation-v1', 'entry': {'conditions': [{'feature': 'return_15m', 'op': 'gt', 'value': 0}, {'feature': 'trade_imbalance', 'op': 'gt', 'value': 0}, {'feature': 'depth10_obi_mean', 'op': 'gt', 'value': 0}], 'confirmations': 1}, 'exit': {'conditions': [{'feature': 'return_15m', 'op': 'lt', 'value': 0}], 'confirmations': 1, 'min_hold_bars': 1}, 'cooldown_bars': 0}"
        nested = source.replace(
            "'conditions': [{'feature': 'return_15m', 'op': 'gt', 'value': 0},",
            "'conditions': [{'all': [{'feature': 'return_15m', 'op': 'gt', 'value': 0}]},",
        )
        result = validate_rule_source(nested)
        self.assertFalse(result.valid)
        self.assertEqual(result.rejection_category, RejectionCategory.SCHEMA)

    def test_calls_expressions_and_multiple_assignments_are_rejected(self):
        call_source = "RULE_SPEC = make_rule()"
        result = validate_rule_source(call_source)
        self.assertFalse(result.valid)
        self.assertEqual(result.rejection_category, RejectionCategory.STRUCTURE)

        expression_source = "RULE_SPEC = {'family_id': 'x' + 'y'}"
        result = validate_rule_source(expression_source)
        self.assertFalse(result.valid)
        self.assertEqual(result.rejection_category, RejectionCategory.STRUCTURE)

        result = validate_rule_source("RULE_SPEC = {}\nRULE_SPEC = {}")
        self.assertFalse(result.valid)
        self.assertEqual(result.rejection_category, RejectionCategory.STRUCTURE)

        class_source = "class Candidate:\n    RULE_SPEC = {}\n"
        result = validate_rule_source(class_source)
        self.assertFalse(result.valid)
        self.assertEqual(result.rejection_category, RejectionCategory.SCHEMA)

    def test_bool_nonfinite_and_out_of_bound_thresholds_are_rejected(self):
        spec = {
            "family_id": "pullback-exhaustion-v1",
            "entry": {"conditions": [
                {"feature": "return_15m", "op": "gt", "value": True},
                {"feature": "close_location", "op": "gt", "value": math.inf},
            ], "confirmations": 1},
            "exit": {"conditions": [{"feature": "return_5m", "op": "lt", "value": -0.2}], "confirmations": 1, "min_hold_bars": 1},
            "cooldown_bars": 0,
        }
        result = validate_rule_dict(spec)
        self.assertFalse(result.valid)
        messages = " ".join(error.message for error in result.errors)
        self.assertIn("bool", messages)
        self.assertIn("finite", messages)
        self.assertIn("between", messages)

    def test_structural_and_numeric_bounds_are_rejected(self):
        result = validate_rule_dict({
            "family_id": "down-streak-risk-off-btc-v1",
            "entry": {"conditions": [], "confirmations": 0},
            "exit": {"conditions": [{"feature": "return_5m", "op": "lt", "value": 0}], "confirmations": 6, "min_hold_bars": 61},
            "cooldown_bars": 31,
        })
        self.assertFalse(result.valid)
        self.assertTrue(any(error.category == RejectionCategory.BOUNDS for error in result.errors))

    def test_exit_any_mode_is_valid_and_preserved(self):
        result = validate_rule_dict({
            "family_id": "down-streak-risk-off-btc-v1",
            "entry": {"conditions": [{"feature": "return_5m", "op": "gt", "value": 0}], "confirmations": 1},
            "exit": {"conditions": [
                {"feature": "return_5m", "op": "lt", "value": -0.02},
                {"feature": "trade_imbalance", "op": "lt", "value": -0.3},
            ], "confirmations": 2, "min_hold_bars": 5, "mode": "any"},
            "cooldown_bars": 2,
        })
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.spec.exit.mode, "any")

    def test_source_class_assignment_and_canonical_equivalence(self):
        first = """RULE_SPEC = {
            'family_id': 'down-streak-risk-off-btc-v1',
            'entry': {'conditions': [{'feature': 'return_5m', 'op': 'gt', 'value': 0}], 'confirmations': 1},
            'exit': {'conditions': [{'feature': 'return_5m', 'op': 'lt', 'value': -0.02}, {'feature': 'trade_imbalance', 'op': 'lt', 'value': -0.3}], 'confirmations': 2, 'min_hold_bars': 5, 'mode': 'any'},
            'cooldown_bars': 2,
        }
        """
        second = """class Candidate:
            RULE_SPEC={'cooldown_bars':2,'exit':{'mode':'any','min_hold_bars':5,'confirmations':2,'conditions':[{'value':-0.3,'op':'lt','feature':'trade_imbalance'},{'value':-0.02,'op':'lt','feature':'return_5m'}]},'entry':{'confirmations':1,'conditions':[{'value':0,'op':'gt','feature':'return_5m'}]},'family_id':'down-streak-risk-off-btc-v1'}
        """
        first_result = validate_rule_source(first)
        second_result = validate_rule_source(second)
        self.assertTrue(first_result.valid, first_result.errors)
        self.assertTrue(second_result.valid, second_result.errors)
        self.assertEqual(first_result.canonical_json, second_result.canonical_json)
        self.assertEqual(rule_source_signature(first), rule_source_signature(second))
        self.assertEqual(json.loads(first_result.canonical_json)["exit"]["mode"], "any")
        self.assertEqual(canonical_rule_json(first_result.spec), first_result.canonical_json)

    def test_integer_and_float_thresholds_have_identical_canonical_signatures(self):
        integer = {
            "family_id": "down-streak-risk-off-btc-v1",
            "entry": {"conditions": [{"feature": "return_5m", "op": "gt", "value": 0}], "confirmations": 1},
            "exit": {"conditions": [{"feature": "return_5m", "op": "lt", "value": -0.02}], "confirmations": 1, "min_hold_bars": 1},
            "cooldown_bars": 0,
        }
        floating = {
            **integer,
            "entry": {"conditions": [{"feature": "return_5m", "op": "gt", "value": 0.0}], "confirmations": 1},
            "cooldown_bars": 0,
        }
        self.assertEqual(canonical_rule_json(integer), canonical_rule_json(floating))
        self.assertEqual(rule_source_signature(integer), rule_source_signature(floating))


if __name__ == "__main__":
    unittest.main()
