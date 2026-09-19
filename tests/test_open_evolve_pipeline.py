from dataclasses import replace
import unittest

from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.model.data import OrderBookDepth10, BookOrder, TradeTick
from nautilus_trader.model.enums import OrderSide, AggressorSide
from nautilus_trader.model.identifiers import TradeId

from experiments.open_evolve.backtest import ExecutionConfig, Fold, Scenario, run_backtest
from experiments.open_evolve.features import FeatureConfig
from experiments.open_evolve.policy import Policy, PolicyLimits, InvalidPolicy
from experiments.open_evolve.contracts import PositionState
from experiments.open_evolve.evaluation import MetricConfig, Fill, Quote, markouts, metrics, ScoreConfig, rank_results


LIMITS = PolicyLimits(8000, 400, 200)
FLAT = "def policy(market, position):\n    return TargetPosition.FLAT\n"
RULE = """def policy(market, position):
    if position.signed_quantity > 0:
        if position.holding_time_ns >= 300000000:
            return TargetPosition.FLAT
        return TargetPosition.LONG
    if market.book_imbalance > 0.1:
        return TargetPosition.LONG
    return TargetPosition.FLAT
"""


def fixture():
    instrument = TestInstrumentProvider.btcusdt_binance()
    start = 1_000_000_000
    depths, trades = [], []
    for i in range(61):
        ts = start + i * 100_000_000
        mid = 100 + i * 0.02
        bids = [BookOrder(OrderSide.BUY, instrument.make_price(mid - 0.01 - j * 0.01),
                          instrument.make_qty(3), j) for j in range(10)]
        asks = [BookOrder(OrderSide.SELL, instrument.make_price(mid + 0.01 + j * 0.01),
                          instrument.make_qty(1), j) for j in range(10)]
        depths.append(OrderBookDepth10(instrument.id, bids, asks, [1] * 10, [1] * 10, 0, i + 1, ts, ts))
        trades.append(TradeTick(instrument.id, instrument.make_price(mid), instrument.make_qty(1),
                                AggressorSide.BUYER, TradeId(str(i)), ts, ts))
    features = FeatureConfig(instrument.id, 10, 200_000_000, 200_000_000,
                             100_000_000, 300_000_000, 300_000_000, 300_000_000, 1.0)
    execution = ExecutionConfig("0.2", "10000", "CASH", False, 500_000_000,
                                 100, 100_000_000, 100, 0.5, 100_000_000)
    fold = Fold("test", start, start + 1_000_000_000, start + 3_500_000_000,
                start + 4_000_000_000, start + 6_000_000_000)
    scenario = Scenario("base", 0, 0, 1_000_000)
    metric = MetricConfig(365 * 24 * 36000, 0, 0, 100, 200_000_000)
    return instrument, trades, depths, features, execution, fold, scenario, metric


class PipelineTests(unittest.TestCase):
    def run_fixture(self, source=RULE, **changes):
        instrument, trades, depths, features, execution, fold, scenario, metric = fixture()
        return run_backtest(instrument, trades, depths, Policy(source, LIMITS), features,
                            changes.get("execution", execution), fold, changes.get("scenario", scenario), metric)

    def test_flat_no_virtual_profit(self):
        result = self.run_fixture(FLAT)
        self.assertEqual(result["status"], "valid", result)
        self.assertEqual(result["metrics"]["net_pnl"], 0)
        self.assertEqual(result["fills"], [])

    def test_actual_nautilus_fills_fees_account_and_reset(self):
        result = self.run_fixture()
        self.assertEqual(result["status"], "valid", result)
        self.assertGreater(result["metrics"]["trade_count"], 0)
        self.assertTrue(all(f["fee"] > 0 for f in result["fills"]))
        self.assertAlmostEqual(sum(result["round_trip_pnls"]), result["metrics"]["net_pnl"])
        self.assertEqual(result, self.run_fixture())

    def test_observation_delay_uses_clock_alerts(self):
        result = self.run_fixture(scenario=Scenario("delayed", 50_000_000, 10_000_000, 1_000_000))
        self.assertEqual(result["status"], "valid", result)
        self.assertGreater(len(result["fills"]), 0)

    def test_future_suffix_does_not_change_prior_decisions_or_fills(self):
        instrument, trades, depths, features, execution, fold, scenario, metric = fixture()
        cutoff = fold.start + 1_000_000_000
        changed = []
        for depth in depths:
            if depth.ts_init <= cutoff:
                changed.append(depth)
            else:
                bids = [BookOrder(OrderSide.BUY, instrument.make_price(float(o.price) + 20), o.size, o.order_id) for o in depth.bids]
                asks = [BookOrder(OrderSide.SELL, instrument.make_price(float(o.price) + 20), o.size, o.order_id) for o in depth.asks]
                changed.append(OrderBookDepth10(instrument.id, bids, asks, [1] * 10, [1] * 10,
                                                0, depth.sequence, depth.ts_event, depth.ts_init))
        before = self.run_fixture()
        after = run_backtest(instrument, trades, changed, Policy(RULE, LIMITS), features,
                             execution, fold, scenario, metric)
        self.assertEqual(after["status"], "valid", after)
        for key in ("fills", "targets"):
            self.assertEqual([r for r in before[key] if r["ts"] <= cutoff],
                             [r for r in after[key] if r["ts"] <= cutoff])

    def test_order_rate_pending_and_forced_exit(self):
        source = "def policy(market, position):\n    return TargetPosition.LONG\n"
        result = self.run_fixture(source, execution=replace(fixture()[4], max_holding_ns=10_000_000_000))
        self.assertEqual(result["status"], "valid", result)
        self.assertEqual(len(result["fills"]), 2)
        self.assertTrue(result["fills"][-1]["forced"])
        self.assertGreater(result["fills"][0]["ts"], fixture()[5].start)

    def test_margin_short_and_flat_before_reversal(self):
        source = """def policy(market, position):
    if position.signed_quantity < 0:
        return TargetPosition.LONG
    if position.signed_quantity > 0:
        return TargetPosition.SHORT
    return TargetPosition.SHORT
"""
        execution = replace(fixture()[4], account_type="MARGIN", allow_short=True)
        result = self.run_fixture(source, execution=execution)
        self.assertEqual(result["status"], "valid", result)
        quantity = 0
        for fill in result["fills"]:
            quantity += fill["side"] * fill["quantity"]
            self.assertLessEqual(abs(quantity), 0.2 + 1e-9)
        self.assertAlmostEqual(quantity, 0)
        self.assertLess(result["fills"][0]["side"], 0)

    def test_invalid_size_and_depth_budget(self):
        with self.assertRaises(ValueError):
            self.run_fixture(execution=replace(fixture()[4], quantity="0.2000001"))
        result = self.run_fixture(execution=replace(fixture()[4], max_depth_fraction=0.001))
        self.assertEqual(result["status"], "valid", result)
        self.assertEqual(result["fills"], [])

    def test_risk_order_limit_failure_is_not_silently_dropped(self):
        result = self.run_fixture(execution=replace(fixture()[4], max_orders=1))
        self.assertEqual(result["status"], "constraint_failed", result)

    def test_policy_exception_classification(self):
        result = self.run_fixture("def policy(market, position):\n    x = 1 / 0\n    return TargetPosition.FLAT\n")
        self.assertEqual(result["status"], "invalid_candidate")

    def test_depth_sweep_produces_partial_fills(self):
        execution = replace(fixture()[4], quantity="2.5")
        result = self.run_fixture(execution=execution)
        self.assertEqual(result["status"], "valid", result)
        self.assertTrue(any(f["quantity"] == 1 for f in result["fills"]))
        self.assertGreater(len(result["fills"]), 2 * result["metrics"]["trade_count"])


class RestrictedPolicyTests(unittest.TestCase):
    def test_forbidden_syntax(self):
        for source in [
            "import os\n" + FLAT,
            "def policy(market, position):\n    return market.__class__\n",
            "def policy(market, position):\n    return market.mid.real\n",
            "def policy(market, position):\n    while True:\n        pass\n",
            "def policy(market, position):\n    return open(1)\n",
            "def policy(market, position):\n    return [1][0]\n",
            "def policy(market, position):\n    return 2 ** 1000000\n",
            "def policy(market, position):\n    market.mid = 1\n    return TargetPosition.FLAT\n",
            "def policy(market, position):\n    return 'x'\n",
            "def policy(market, position):\n    return 1e999\n",
        ]:
            with self.subTest(source=source), self.assertRaises(InvalidPolicy):
                Policy(source, LIMITS)

    def test_short_circuit_and_budget(self):
        from experiments.open_evolve.features import FeatureEngine
        instrument, trades, depths, config, *_ = fixture()
        market = FeatureEngine(config).update(depths[0], available_at=depths[0].ts_init, event_ordinal=0).market
        position = PositionState(0, None, 0, None, False)
        source = "def policy(market, position):\n    if market.trade_imbalance is not None and market.trade_imbalance > 0:\n        return TargetPosition.LONG\n    return TargetPosition.FLAT\n"
        self.assertEqual(Policy(source, LIMITS)(market, position, allow_short=False).value, 0)
        with self.assertRaises(InvalidPolicy):
            Policy(source, replace(LIMITS, max_steps=1))(market, position, allow_short=False)


class MetricTests(unittest.TestCase):
    def test_markout_does_not_use_next_quote_or_same_time_future_event(self):
        fills = [Fill(10, 1, 1, 2, 100, 0.2, True, False)]
        quotes = [Quote(10, 0, 100), Quote(10, 2, 101), Quote(20, 3, 102), Quote(100, 4, 200)]
        result = markouts(fills, quotes, 10, 10)
        self.assertAlmostEqual(result["weighted_mean"], 200)
        self.assertAlmostEqual(result["rows"][0]["mid_move_bps"], 200)
        self.assertAlmostEqual(result["rows"][0]["net_fill_bps"], 190)
        self.assertEqual(markouts(fills, quotes, 50, 10)["coverage"], 0)

    def test_invalid_quote_blocks_previous_quote(self):
        result = markouts([Fill(10, 1, 1, 1, 100, 0, True, False)],
                         [Quote(10, 0, 100), Quote(20, 2, None)], 10, 100)
        self.assertEqual(result["coverage"], 0)

    def test_pnl_drawdown_turnover_and_hard_gates(self):
        config = MetricConfig(1, 0, 0, 100, 100)
        fills = [Fill(1, 0, 1, 1, 100, 0, True, False)]
        result = metrics([100, 110, 99, 105], [10, -5], fills, config)
        self.assertEqual(result["net_pnl"], 5)
        self.assertAlmostEqual(result["max_drawdown"], 0.1)
        self.assertEqual(result["profit_factor"], 2)
        self.assertEqual(result["turnover"], 1)
        scores = ScoreConfig(1, 0.2, 10, -100, 0.5, {"median_sharpe": 1}, {"median_sharpe": 1}, 100)
        cell = {"status": "valid", "scenario": "base", "metrics": result,
                "markout": {h: {"coverage": 1, "weighted_mean": 1} for h in ("100ms", "1s")}}
        self.assertEqual(rank_results([cell], 1, scores)["status"], "valid")
        self.assertEqual(rank_results([cell], 1, replace(scores, min_trades=10))["status"], "constraint_failed")


if __name__ == "__main__":
    unittest.main()
