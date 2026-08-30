import unittest


class EvolutionBacktestTests(unittest.TestCase):
    def test_synthetic_nautilus_run_fills_ioc_charges_fees_and_forces_close(self):
        from evolution.backtest import run_candidate
        from evolution.market_state import EvolutionMarketState

        states = []
        for index, price in enumerate((100, 100, 100, 100, 100, 100)):
            ts_event = (index + 1) * 60_000_000_000
            states.append(EvolutionMarketState(
                "BTCUSDT.BINANCE", price, price, price, price, 1, 2, 1, 1,
                0.5, 0.5, 0, 0, 0, 0, 0, 0, price - 0.1, price + 0.1, 20,
                ts_event, ts_event + 2,
            ))
        result = run_candidate("evolution/baselines/buy_and_hold.py", "BTCUSDT.BINANCE", states)
        self.assertEqual(result.fill_count, 2)
        self.assertEqual(result.position_count, 1)
        self.assertLess(result.metrics.net_return, 0)
        self.assertGreater(result.metrics.max_drawdown, 0)
        self.assertEqual(len(result.metrics.daily_returns), 1)
        self.assertAlmostEqual(result.metrics.daily_returns[0], result.metrics.net_return)
        self.assertFalse(result.metrics.rejected)

    def test_one_second_signal_delay_uses_the_next_bbo(self):
        from evolution.backtest import _with_init_delay
        from evolution.market_state import EvolutionMarketState

        ts_event = 60_000_000_000
        state = EvolutionMarketState(
            "BTCUSDT.BINANCE", 100, 100, 100, 100, 1, 1, 1, 0,
            1, 0, 1, 1, 0, 0, 0, 0, 99.9, 100.1, 20,
            ts_event, ts_event + 2,
        )
        delayed = _with_init_delay(state, 1)
        self.assertEqual(delayed.ts_event, ts_event)
        self.assertEqual(delayed.ts_init, ts_event + 1_000_000_002)


if __name__ == "__main__":
    unittest.main()
