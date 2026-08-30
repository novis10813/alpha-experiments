import unittest


class EvolutionMetricsTests(unittest.TestCase):
    def test_sharpe_fitness_and_activity_gate(self):
        from evolution.metrics import FoldMetrics
        from evolution.metrics import REJECTED_SCORE
        from evolution.metrics import aggregate_folds
        from evolution.metrics import annualized_sharpe

        folds = [FoldMetrics(value, drawdown, 1.2, 4, 8, 0.5, daily_returns=returns) for value, drawdown, returns in [
            (0.10, 0.02, (0.01, 0.02)), (0.05, 0.03, (-0.01, 0.01)),
            (0.02, 0.04, (0.00, 0.01)), (0.04, 0.05, (0.02, -0.01)),
            (-0.01, 0.06, (-0.02, 0.01)),
        ]]
        aggregate = aggregate_folds(folds)
        self.assertAlmostEqual(
            aggregate.combined_score,
            annualized_sharpe(value for fold in folds for value in fold.daily_returns),
        )
        self.assertEqual(aggregate.to_open_evolve()["sharpe_ratio"], aggregate.combined_score)
        self.assertEqual(aggregate.closed_positions, 20)
        rejected = aggregate_folds([FoldMetrics(0.1, 0.01, 1, 4, 8, 0.1)] * 3)
        self.assertEqual(rejected.combined_score, REJECTED_SCORE)

    def test_sharpe_uses_daily_sample_volatility(self):
        from evolution.metrics import annualized_sharpe

        self.assertAlmostEqual(annualized_sharpe((0.01, -0.01, 0.02)), 8.33809387832792)
        self.assertEqual(annualized_sharpe((0.0, 0.0)), 0.0)

    def test_screen_nan_and_ten_percent_loss_rules(self):
        from evolution.metrics import FoldMetrics
        from evolution.metrics import screen_passes

        self.assertTrue(screen_passes(FoldMetrics(-0.099, 0.1, 0, 1, 2, 0.1)))
        self.assertFalse(screen_passes(FoldMetrics(-0.101, 0.1, 0, 1, 2, 0.1)))
        with self.assertRaises(ValueError):
            FoldMetrics(float("nan"), 0.1, 0, 1, 2, 0.1)

    def test_drawdown_and_profit_factor(self):
        from evolution.metrics import max_drawdown
        from evolution.metrics import profit_factor

        self.assertAlmostEqual(max_drawdown([100, 120, 90, 110]), 0.25)
        self.assertEqual(profit_factor([10, -4, 2, -2]), 2)


if __name__ == "__main__":
    unittest.main()
