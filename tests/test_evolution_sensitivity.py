import unittest


class EvolutionSensitivityTests(unittest.TestCase):
    def test_fee_parameter_changes_net_but_not_gross_or_turnover(self):
        from evolution.backtest import run_candidate

        free = run_candidate(
            "evolution/baselines/buy_and_hold.py", "BTCUSDT.BINANCE", _states(), fee_rate=0,
        )
        costly = run_candidate(
            "evolution/baselines/buy_and_hold.py", "BTCUSDT.BINANCE", _states(), fee_rate=0.0015,
        )
        self.assertAlmostEqual(free.diagnostics.gross_return, costly.diagnostics.gross_return)
        self.assertAlmostEqual(free.diagnostics.turnover, costly.diagnostics.turnover)
        self.assertEqual(free.diagnostics.fee_drag, 0)
        self.assertGreater(costly.diagnostics.fee_drag, 0)
        self.assertGreater(free.metrics.net_return, costly.metrics.net_return)

    def test_labels_detect_cost_fragility(self):
        from evolution.sensitivity import sensitivity_labels

        scenarios = []
        for delay in (0, 1, 5):
            for fee in (0, 5, 10, 15):
                sharpe = 1.0 if fee == 0 else -1.0
                scenarios.append({
                    "fee_bps": fee,
                    "delay_seconds": delay,
                    "metrics": {"aggregate": {"net_sharpe": sharpe}},
                })
        self.assertIn("cost_fragile", sensitivity_labels(scenarios))


def _states():
    from evolution.market_state import EvolutionMarketState

    states = []
    for index, price in enumerate((100, 101, 102)):
        ts = (index + 1) * 60_000_000_000
        states.append(EvolutionMarketState(
            "BTCUSDT.BINANCE", price, price, price, price, 1, 2, 1, 1,
            0.5, 0.5, 0, 0, 0, 0, 0, 0, price - 0.1, price + 0.1, 20, ts, ts + 2,
        ))
    return states


if __name__ == "__main__":
    unittest.main()
