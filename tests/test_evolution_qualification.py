import unittest


class EvolutionQualificationTests(unittest.TestCase):
    def test_negative_executable_candidate_is_disqualified(self):
        from evolution.qualification import qualify_discovery

        rerank = _rerank(-1.0, (-0.01,) * 5)
        sensitivity = {"candidate_id": "c1", "programs": {"executable_champion": {"labels": ["economically_rejected"]}}}
        result = qualify_discovery(rerank, sensitivity, "family-v1")
        self.assertFalse(result.qualified)
        self.assertIn("non_positive_executable_sharpe", result.reasons)
        self.assertIn("non_positive_median_fold_return", result.reasons)
        self.assertIn("insufficient_positive_folds", result.reasons)

    def test_all_registered_gates_can_pass(self):
        from evolution.qualification import qualify_discovery

        rerank = _rerank(1.0, (0.01, 0.02, 0.01, -0.01, 0.03))
        sensitivity = {"candidate_id": "c1", "programs": {"executable_champion": {"labels": ["cost_robust"]}}}
        self.assertTrue(qualify_discovery(rerank, sensitivity, "family-v1").qualified)


def _rerank(sharpe, returns):
    return {"candidates": [{
        "candidate_id": "c1",
        "deterministic": True,
        "executable": {
            "aggregate": {"net_sharpe": sharpe},
            "folds": [
                {"metrics": {"net_return": value, "closed_positions": 4}}
                for value in returns
            ],
        },
    }]}


if __name__ == "__main__":
    unittest.main()
