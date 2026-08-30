import unittest


class EvolutionSelectionTests(unittest.TestCase):
    def test_rejected_and_fixed_low_score_candidates_are_excluded_from_promotion_ranking(self):
        from evolution.metrics import AggregateMetrics, REJECTED_SCORE
        from evolution.selection import CandidateResult, rank_for_validation

        def candidate(candidate_id, score):
            return CandidateResult(
                candidate_id,
                AggregateMetrics(score, 0, 0, 0, 0, 0, 0, 0, 0),
            )

        ranked = rank_for_validation([
            candidate("rejected", REJECTED_SCORE),
            candidate("fixed-low", REJECTED_SCORE),
            candidate("eligible", 1.0),
        ])
        self.assertEqual([item.candidate_id for item in ranked], ["eligible"])

    def test_rejected_and_fixed_low_score_candidates_are_not_parent_when_eligible_archive_exists(self):
        from openevolve.config import Config, DatabaseConfig
        from openevolve.database import Program, ProgramDatabase
        from evolution.metrics import REJECTED_SCORE

        config = Config()
        config.database = DatabaseConfig(
            archive_size=1,
            num_islands=1,
            population_size=10,
            feature_dimensions=["complexity"],
            exploration_ratio=0.0,
            exploitation_ratio=1.0,
            random_seed=7,
        )
        database = ProgramDatabase(config.database)
        database.add(Program("rejected", "rejected", metrics={"combined_score": REJECTED_SCORE}))
        database.add(Program("fixed-low", "fixed-low", metrics={"combined_score": REJECTED_SCORE}))
        database.add(Program("eligible", "eligible", metrics={"combined_score": 1.0}))

        self.assertEqual(database.archive, {"eligible"})
        self.assertEqual({database.sample()[0].id for _ in range(10)}, {"eligible"})


if __name__ == "__main__":
    unittest.main()
