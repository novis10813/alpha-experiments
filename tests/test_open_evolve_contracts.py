from dataclasses import FrozenInstanceError
import unittest

from experiments.open_evolve.contracts import PositionState, TargetPosition, validate_target


class PolicyContractTests(unittest.TestCase):
    def test_output_must_be_enum_and_respect_short_permission(self):
        for target in TargetPosition:
            self.assertIs(validate_target(target, allow_short=True), target)
        for output in [None, True, 0, 1, -1, 1.0, "LONG", {}, [1]]:
            with self.subTest(output=output), self.assertRaises(ValueError):
                validate_target(output, allow_short=True)
        with self.assertRaises(ValueError):
            validate_target(TargetPosition.SHORT, allow_short=False)
        self.assertIs(validate_target(TargetPosition.FLAT, allow_short=False), TargetPosition.FLAT)

    def test_position_supports_partial_fill_and_missing_mark(self):
        position = PositionState(0.25, 100, 10, None, True)
        self.assertEqual(position.signed_quantity, 0.25)
        with self.assertRaises(FrozenInstanceError):
            position.signed_quantity = 1
        self.assertEqual(PositionState(0, None, 0, None, False).holding_time_ns, 0)

    def test_reject_inconsistent_or_nonfinite_position(self):
        for values in [
            (0, 100, 0, None, False), (0, None, 1, None, False),
            (0, None, 0, 1, False), (1, None, 0, None, False),
            (1, 0, 0, None, False), (float("nan"), 100, 0, None, False),
            (1, 100, -1, None, False), (1, 100, 0, float("inf"), False),
            (1, 100, 0, 0, 1),
        ]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                PositionState(*values)


if __name__ == "__main__":
    unittest.main()
