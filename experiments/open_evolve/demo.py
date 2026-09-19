"""Offline end-to-end synthetic smoke run; NOT evidence of trading edge.

uv run python -m experiments.open_evolve.demo --output outputs/open_evolve/demo
"""

import argparse
from dataclasses import asdict
from pathlib import Path

from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.model.data import BookOrder, OrderBookDepth10, TradeTick
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import TradeId

from experiments.open_evolve.backtest import Fold, Scenario, ExecutionConfig
from experiments.open_evolve.features import FeatureConfig
from experiments.open_evolve.policy import PolicyLimits
from experiments.open_evolve.evaluation import MetricConfig, ScoreConfig
from experiments.open_evolve.cli import evaluator
from experiments.open_evolve.search import EvolutionSearch, finalize, fingerprint


SEED = """def policy(market, position):
    if position.signed_quantity > 0:
        if position.holding_time_ns >= 300000000:
            return TargetPosition.FLAT
        return TargetPosition.LONG
    if market.book_imbalance > 0.1:
        return TargetPosition.LONG
    return TargetPosition.FLAT
"""


def data(instrument, offset):
    depths, trades = [], []
    for i in range(81):
        ts = offset + i * 100_000_000
        mid = 100 + i * 0.2
        bids = [BookOrder(OrderSide.BUY, instrument.make_price(mid - 0.01 - j * 0.01),
                          instrument.make_qty(3), j) for j in range(10)]
        asks = [BookOrder(OrderSide.SELL, instrument.make_price(mid + 0.01 + j * 0.01),
                          instrument.make_qty(1), j) for j in range(10)]
        depths.append(OrderBookDepth10(instrument.id, bids, asks, [1] * 10, [1] * 10, 0, i + 1, ts, ts))
        trades.append(TradeTick(instrument.id, instrument.make_price(mid), instrument.make_qty(1),
                                AggressorSide.BUYER, TradeId(str(i)), ts, ts))
    fold = Fold(str(offset), offset, offset + 1_000_000_000, offset + 5_000_000_000,
                offset + 6_000_000_000, offset + 8_000_000_000)
    return fold, trades, depths, fingerprint({"generator": "synthetic-trend-v1", "offset": offset})


def run_demo(output, backend="legacy"):
    instrument = TestInstrumentProvider.btcusdt_binance()
    feature_config = FeatureConfig(instrument.id, 10, 200_000_000, 200_000_000, 100_000_000,
                                   300_000_000, 300_000_000, 300_000_000, 1)
    config = {
        "features": {k: v for k, v in asdict(feature_config).items() if k != "instrument_id"},
        "execution": asdict(ExecutionConfig("0.2", "10000", "CASH", False, 500_000_000,
                                              100, 100_000_000, 100, 0.5, 100_000_000)),
        "metrics": asdict(MetricConfig(365 * 24 * 36000, 0, 0, 100, 200_000_000)),
        "scenarios": [asdict(Scenario("base", 0, 0, 1_000_000)),
                      asdict(Scenario("stress", 50_000_000, 10_000_000, 20_000_000))],
    }
    score = ScoreConfig(1, 0.5, 100, -100, 0.8,
                         {"median_sharpe": 1, "worst_sharpe": 0.5, "complexity": -0.01},
                         {"median_sharpe": 100, "worst_sharpe": 100, "complexity": 100}, 10)
    loaded = [data(instrument, offset) for offset in (1_000_000_000, 11_000_000_000)]
    common = dict(output=output, contract={"synthetic_only": True, "config": config},
                  limits=PolicyLimits(8000, 400, 300), score=score,
                  expected_cells={(f.name, s["name"]) for f, *_ in loaded for s in config["scenarios"]},
                  evaluate=evaluator(config, instrument, loaded))
    if backend == "openevolve":
        from openevolve.config import LLMModelConfig
        from openevolve.llm.ensemble import LLMEnsemble
        from experiments.open_evolve.cli import SYSTEM_PROMPT
        from experiments.open_evolve.openevolve_backend import OpenEvolveSearch, SearchSettings
        class OfflineModel:
            def __init__(self):
                self.model = "deterministic-smoke"
            async def generate_with_context(self, system_message, messages, **kwargs):
                return SEED.replace("300000000", "400000000")
        ensemble = LLMEnsemble([LLMModelConfig(name="deterministic-smoke", init_client=lambda cfg: OfflineModel())])
        search = OpenEvolveSearch(settings=SearchSettings(), system_prompt=SYSTEM_PROMPT, **common)
        selection = search.run([SEED], budget=3, ensemble=ensemble)
    elif backend == "legacy":
        search = EvolutionSearch(**common)
        def propose(request):
            anchor = request["best"] or request["latest"]
            parent = anchor["source"] if anchor else SEED
            return parent.replace("300000000", "400000000")
        selection = search.run([SEED], budget=3, propose=propose)
    else:
        raise ValueError("unknown demo backend")
    if selection["status"] == "selected":
        finalize(output, expected_contract_hash=selection["contract_hash"],
                 evaluate_holdout=lambda policy, contract: evaluator(
                     config, instrument, [data(instrument, 21_000_000_000)])(policy))
    return selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=("legacy", "openevolve"), default="openevolve")
    args = parser.parse_args()
    import json
    print(json.dumps(run_demo(args.output, backend=args.backend), indent=2))


if __name__ == "__main__":
    main()
