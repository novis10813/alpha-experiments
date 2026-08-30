import unittest
from pathlib import Path


class CandidateValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = Path("evolution/initial_program.py").read_text(encoding="utf-8")

    def test_reference_candidate_is_valid_and_hash_is_stable(self):
        from evolution.candidate import skeleton_hash
        from evolution.candidate import validate_candidate

        result = validate_candidate(self.reference, self.reference)
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(skeleton_hash(self.reference), skeleton_hash(self.reference))

    def test_syntax_forbidden_import_and_reflection_are_rejected(self):
        from evolution.candidate import EVOLVE_END
        from evolution.candidate import EVOLVE_START
        from evolution.candidate import validate_candidate

        prefix, rest = self.reference.split(EVOLVE_START, 1)
        _, suffix = rest.split(EVOLVE_END, 1)
        for block, expected in [
            ("\n    def broken(:\n        pass\n", "syntax error"),
            ("\n    import os\n", "forbidden import"),
            ("\n    def on_data(self, data):\n        return self.__dict__\n", "forbidden attribute"),
        ]:
            result = validate_candidate(prefix + EVOLVE_START + block + EVOLVE_END + suffix, self.reference)
            self.assertFalse(result.valid)
            self.assertIn(expected, " ".join(result.errors))

    def test_source_signature_handles_class_level_assignment_formatting_and_numeric_equivalence(self):
        from evolution.signatures import source_signature

        reference = Path("evolution/families/down-streak-risk-off-btc-v1/initial_program.py").read_text(encoding="utf-8")
        reordered = reference.replace('"value": 0.0', '"value": 0', 1)
        self.assertEqual(source_signature(reference), source_signature(reordered))

    def test_source_signature_ignores_comments_and_formatting_but_not_literals(self):
        from evolution.candidate import EVOLVE_END, EVOLVE_START
        from evolution.signatures import source_signature

        prefix, rest = self.reference.split(EVOLVE_START, 1)
        block, suffix = rest.split(EVOLVE_END, 1)
        comments = block.replace("#", "# formatting comment\n        #", 1)
        compact = "\n".join(line.rstrip() for line in comments.splitlines())
        changed = block.replace("maxlen=240", "maxlen=241", 1)
        self.assertEqual(
            source_signature(prefix + EVOLVE_START + block + EVOLVE_END + suffix),
            source_signature(prefix + EVOLVE_START + compact + EVOLVE_END + suffix),
        )
        self.assertNotEqual(
            source_signature(prefix + EVOLVE_START + block + EVOLVE_END + suffix),
            source_signature(prefix + EVOLVE_START + changed + EVOLVE_END + suffix),
        )

    def test_skeleton_change_and_direct_order_factory_are_rejected(self):
        from evolution.candidate import validate_candidate

        changed = self.reference.replace(
            "from evolution.strategy_base import EvolutionStrategyConfig",
            "from evolution.strategy_base import StrategyConfig",
            1,
        )
        self.assertIn("skeleton", " ".join(validate_candidate(changed, self.reference).errors))
        direct = self.reference.replace(
            "        state: EvolutionMarketState = data\n",
            "        state: EvolutionMarketState = data\n        self.order_factory.market()\n",
        )
        self.assertIn("only place orders", " ".join(validate_candidate(direct, self.reference).errors))


if __name__ == "__main__":
    unittest.main()
