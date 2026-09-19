"""CLI for catalog-backed evolution and one-shot final holdout.

Configuration supplies all numeric research choices. No credentials are stored
in it. The optional proposer uses an OpenAI-compatible chat-completions endpoint;
model credentials are consumed here, never inside candidate execution.
"""

import argparse
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from urllib.request import Request, urlopen

import nautilus_trader
from nautilus_trader.model.data import OrderBookDepth10
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Currency, Money, Price, Quantity

from data.nautilus_catalog import make_catalog
from experiments.open_evolve.backtest import Fold, Scenario, ExecutionConfig, run_backtest
from experiments.open_evolve.features import FeatureConfig, FeatureEngine, SCHEMA_VERSION
from experiments.open_evolve.policy import PolicyLimits
from experiments.open_evolve.evaluation import MetricConfig, ScoreConfig
from experiments.open_evolve.search import EvolutionSearch, finalize, fingerprint


SYSTEM_PROMPT = """Return only Python source for def policy(market, position).
The trading simulator, features, sizing, execution and risk are fixed.
Use numeric/boolean/None constants, local scalar assignments, if/else, return,
+ - * / %, comparisons, and/or/not, conditional expressions, abs/min/max only.
No imports, loops, containers, subscripts, globals, nested attributes or functions.
Return TargetPosition.FLAT, LONG, or SHORT (only when allowed by the contract).
Market fields: ready, book_valid, book_age_ns, trade_age_ns, mid, spread_bps,
microprice_offset_bps, book_imbalance, ofi, trade_imbalance,
known_trade_fraction, log_return, realized_volatility.
Position fields: signed_quantity, average_entry_price, holding_time_ns,
unrealized_return_bps, order_pending.

The policy is called only when market.ready is True and data is fresh.
Market numeric fields are populated then. Position average_entry_price and
unrealized_return_bps can still be None when flat: guard them before comparing.
A comparison against None makes the whole candidate invalid.
Units: *_ns and holding_time_ns are nanoseconds (1 second = 1e9 ns).
*_bps are basis points (1 bp = 0.0001 return). log_return and realized_volatility
are dimensionless log-return quantities, NOT bps. book_imbalance and
trade_imbalance are in [-1, 1]; known_trade_fraction is in [0, 1].
OFI is unnormalized base-quantity flow. Microprice uses best bid/ask sizes:
abs(microprice_offset_bps) <= spread_bps / 2, up to floating-point rounding.
Thus microprice_offset_bps > 1 AND spread_bps < 2 is infeasible. Do not rely on absolute
timestamps, fold identity, or file paths. Use position.holding_time_ns and
unrealized_return_bps for exit logic; use the microstructure fields for
timing/entry logic.

You receive evolution-only evaluation feedback (per-fold metrics, markouts,
fitness, violations). Use it to improve the policy while staying simple and
interpretable; avoid overfitting to a single fold. Never change the interface.
"""


class ChatProposer:
    def __init__(self, model, *, temperature, max_tokens, allow_short):
        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens
        self.allow_short = allow_short
        self.endpoint = os.environ["EVOLVE_MODEL_ENDPOINT"]
        self.key = os.environ["EVOLVE_MODEL_API_KEY"]

    def __call__(self, feedback):
        request = Request(
            self.endpoint,
            data=json.dumps({
                "model": self.model, "temperature": self.temperature, "max_tokens": self.max_tokens,
                "chat_template_kwargs": {"enable_thinking": False},
                "messages": [{"role": "system", "content": SYSTEM_PROMPT + f"\nallow_short={self.allow_short}"},
                             {"role": "user", "content": json.dumps(feedback, allow_nan=False)}],
            }).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"},
        )
        with urlopen(request, timeout=120) as response:
            payload = response.read(1_000_001)
        if len(payload) > 1_000_000:
            raise ValueError("model response too large")
        message = json.loads(payload)["choices"][0]["message"]
        source = (message.get("content") or "").strip()
        if not source:
            raise ValueError("model returned empty content")
        if source.startswith("```"):
            lines = source.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            source = "\n".join(lines).strip()
        return source


def implementation_hash():
    digest = sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    digest.update(Path("uv.lock").read_bytes())
    return digest.hexdigest()


def validate_config(config):
    required = {"instrument_id", "features", "execution", "metrics", "score", "limits",
                "folds", "holdout", "scenarios", "budget", "seeds", "model",
                "timestamp_model", "accounting_model", "embargo_ns", "max_events"}
    if set(config) - {"search"} != required:
        raise ValueError(f"config keys must be {sorted(required)} plus optional search")
    search = config.get("search", {"backend": "openevolve"})
    if not isinstance(search, dict) or search.get("backend") not in ("legacy", "openevolve"):
        raise ValueError("search.backend must be legacy or openevolve")
    if search["backend"] == "legacy":
        if set(search) != {"backend"}:
            raise ValueError("legacy backend has no population settings")
    else:
        from experiments.open_evolve.openevolve_backend import SearchSettings
        SearchSettings(**{k: v for k, v in search.items() if k != "backend"})
    if config["timestamp_model"] != "ts_init_receive_book_before_trade":
        raise ValueError("unsupported timestamp model; verify ts_init receive semantics first")
    if config["accounting_model"] != "linear_quote_no_funding_no_borrow":
        raise ValueError("unsupported accounting model")
    folds = [Fold(**f) for f in config["folds"]]
    holdout = Fold(**config["holdout"])
    if len(folds) < 2 or len({f.name for f in folds + [holdout]}) != len(folds) + 1:
        raise ValueError("need at least two uniquely named evolution folds and a separate holdout")
    if config["embargo_ns"] < 0 or config["max_events"] <= 0:
        raise ValueError("invalid embargo or event budget")
    for left, right in zip(folds + [holdout], (folds + [holdout])[1:]):
        if right.warmup_start < left.tail_end + config["embargo_ns"]:
            raise ValueError("fold warmup/scoring/tails must be disjoint with embargo")
    scenarios = [Scenario(**s) for s in config["scenarios"]]
    if len(scenarios) < 2 or len({s.name for s in scenarios}) != len(scenarios):
        raise ValueError("need uniquely named baseline and stress scenarios")
    execution = ExecutionConfig(**config["execution"])
    features = FeatureConfig(instrument_id=InstrumentId.from_str(config["instrument_id"]), **config["features"])
    for fold in folds + [holdout]:
        if (fold.start - fold.warmup_start < features.warmup_ns
                or (fold.end - fold.start) % execution.equity_interval_ns):
            raise ValueError("fold warmup or equity grid is incompatible with configuration")
        if execution.max_holding_ns > fold.end - fold.start:
            raise ValueError("max_holding_ns exceeds fold scoring duration")
        if any(fold.end - fold.entry_end <= s.observation_ns + s.compute_ns + s.order_ns for s in scenarios):
            raise ValueError("exit buffer must exceed each scenario latency")
    metric_cfg = MetricConfig(**config["metrics"])
    score_cfg = ScoreConfig(**config["score"])
    PolicyLimits(**config["limits"])
    if not set(score_cfg.markout_horizons) <= set(metric_cfg.markout_horizons):
        raise ValueError("score markout horizons must be configured in metrics.markout_horizons")
    if not config["seeds"] or config["budget"] < len(config["seeds"]):
        raise ValueError("invalid seed population/budget")
    model = config["model"]
    if (set(model) != {"model", "temperature", "max_tokens"} or not model["model"]
            or not 0 <= model["temperature"] <= 2 or model["max_tokens"] <= 0):
        raise ValueError("invalid model configuration")


def resolve_instrument(catalog, instrument_id):
    """Return (instrument, source) for the pinned single-instrument contract.

    This catalog layout stores no instrument data, so fall back to the fixed
    Binance spot BTCUSDT spec. load_fold verifies that spec against real data.
    """
    stored = catalog.instruments(instrument_ids=[str(instrument_id)])
    if len(stored) == 1:
        return stored[0], "catalog"
    if len(stored) > 1:
        raise ValueError("ambiguous instrument versions in catalog")
    if instrument_id != InstrumentId.from_str("BTCUSDT.BINANCE"):
        raise ValueError("no stored instrument; pinned spec only supports BTCUSDT.BINANCE")
    usdt = Currency.from_str("USDT")
    spec = CurrencyPair(
        instrument_id=instrument_id,
        raw_symbol=Symbol("BTCUSDT"),
        base_currency=Currency.from_str("BTC"),
        quote_currency=usdt,
        price_precision=2,
        size_precision=5,
        price_increment=Price.from_str("0.01"),
        size_increment=Quantity.from_str("0.00001"),
        ts_event=0,
        ts_init=0,
        multiplier=Quantity.from_int(1),
        min_quantity=Quantity.from_str("0.00001"),
        min_notional=Money(10, usdt),
        maker_fee=Decimal("0.001"),
        taker_fee=Decimal("0.001"),
    )
    return spec, "pinned-spec"


def load_fold(catalog, instrument_id, fold, max_events):
    kwargs = {"start": fold.warmup_start, "end": fold.tail_end}
    trades = catalog.trade_ticks(instrument_ids=[instrument_id], **kwargs)
    depths = catalog.query(OrderBookDepth10, identifiers=[str(instrument_id)], **kwargs)
    if not trades or not depths or len(trades) + len(depths) > max_events:
        raise ValueError("empty data or event memory budget exceeded")
    # Preserve within-stream source order and reject duplicates instead of silently sorting.
    digest = sha256()
    for stream in (depths, trades):
        previous_time, same_time = None, set()
        for event in stream:
            if previous_time is not None and event.ts_init < previous_time:
                raise ValueError("catalog stream is not ordered by ts_init")
            encoded = json.dumps(type(event).to_dict(event), sort_keys=True).encode()
            if event.ts_init != previous_time:
                same_time.clear()
            if encoded in same_time:
                raise ValueError("duplicate market event")
            same_time.add(encoded)
            previous_time = event.ts_init
            digest.update(encoded)
        if stream[0].ts_init > fold.start or stream[-1].ts_init < fold.end:
            raise ValueError("catalog does not cover requested scoring interval")
    if depths[-1].ts_init < fold.end + 1_000_000_000:
        raise ValueError("depth data does not cover the final 1s diagnostic horizon")
    # Verify the instrument spec against observed data precision.
    def two_decimals(price) -> bool:
        return abs(round(float(price), 2) - float(price)) <= 1e-9
    if not all(two_decimals(sample.price) for sample in trades[:5000]):
        raise ValueError("observed trade price violates pinned 2dp spec")
    for sample in depths[:5000]:
        for side in (sample.bids, sample.asks):
            if not all(two_decimals(level.price) for level in side):
                raise ValueError("observed book price violates pinned 2dp spec")
    return trades, depths, digest.hexdigest()


def evaluator(config, instrument, loaded):
    features = FeatureConfig(instrument_id=instrument.id, **config["features"])
    execution = ExecutionConfig(**config["execution"])
    metric_config = MetricConfig(**config["metrics"])
    scenarios = [Scenario(**s) for s in config["scenarios"]]
    # Compute immutable causal snapshots once per fold. Only the wrapper reads this cache.
    cache = {}
    for fold, trades, depths, _ in loaded:
        engine = FeatureEngine(features)
        ordered = sorted([e for e in [*depths, *trades]
                          if fold.warmup_start <= e.ts_init <= fold.tail_end], key=lambda e: e.ts_init)
        cache[fold.name] = [engine.update(e, available_at=e.ts_init, event_ordinal=i)
                            for i, e in enumerate(ordered)]

    def evaluate(policy):
        return [run_backtest(instrument, trades, depths, policy, features, execution, fold, scenario,
                             metric_config, snapshots=cache[fold.name])
                for fold, trades, depths, _ in loaded for scenario in scenarios]
    return evaluate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-config")
    validate.add_argument("config", type=Path)
    evolve = sub.add_parser("evolve")
    evolve.add_argument("config", type=Path)
    evolve.add_argument("output", type=Path)
    final = sub.add_parser("finalize")
    final.add_argument("run", type=Path)
    final.add_argument("--contract-hash", required=True)
    args = parser.parse_args(argv)
    if args.command == "validate-config":
        validate_config(json.loads(args.config.read_text()))
        print("Configuration structure is valid; data coverage and timestamp semantics are not verified.")
        return
    if args.command == "evolve":
        config = json.loads(args.config.read_text())
        validate_config(config)
        catalog = make_catalog()
        iid = InstrumentId.from_str(config["instrument_id"])
        instrument, instrument_source = resolve_instrument(catalog, iid)
        loaded = [(fold, *load_fold(catalog, iid, fold, config["max_events"]))
                  for fold in map(lambda f: Fold(**f), config["folds"])]
        seeds = [Path(path).read_text() for path in config["seeds"]]
        contract = {"config": config, "implementation_hash": implementation_hash(),
                    "nautilus_version": nautilus_trader.__version__, "python_version": sys.version,
                    "feature_schema": SCHEMA_VERSION, "system_prompt": SYSTEM_PROMPT,
                    "instrument_source": instrument_source,
                    "instrument_hash": fingerprint(type(instrument).to_dict(instrument)),
                    "data_hashes": {fold.name: digest for fold, _, _, digest in loaded}}
        search_config = config.get("search", {"backend": "openevolve"})
        common = dict(output=args.output, contract=contract,
                      limits=PolicyLimits(**config["limits"]), score=ScoreConfig(**config["score"]),
                      expected_cells={(f["name"], s["name"]) for f in config["folds"] for s in config["scenarios"]},
                      evaluate=evaluator(config, instrument, loaded))
        if search_config["backend"] == "openevolve":
            from experiments.open_evolve.openevolve_backend import OpenEvolveSearch, SearchSettings, make_ensemble
            settings = SearchSettings(**{k: v for k, v in search_config.items() if k != "backend"})
            # Explicit allowlist: no holdout dates, paths or raw catalog data in prompts.
            context = {"allow_short": config["execution"]["allow_short"],
                       "quantity": config["execution"]["quantity"],
                       "max_holding_ns": config["execution"]["max_holding_ns"],
                       "taker_fee_bps_per_side": float(instrument.taker_fee) * 10_000,
                       "features": config["features"], "score": config["score"]}
            prompt = SYSTEM_PROMPT + "\nFixed trading context:\n" + json.dumps(context, allow_nan=False)
            contract["system_prompt"] = prompt
            search = OpenEvolveSearch(settings=settings, system_prompt=prompt, **common)
            ensemble = None if config["budget"] == len(seeds) else make_ensemble(config["model"], settings)
            try:
                selection = search.run(seeds, budget=config["budget"], ensemble=ensemble)
            finally:
                if ensemble:
                    for model in ensemble.models:
                        model.client.close()
        else:
            contract["search"] = {"backend": "legacy"}
            search = EvolutionSearch(**common)
            proposer = None if config["budget"] == len(seeds) else ChatProposer(
                **config["model"], allow_short=config["execution"]["allow_short"])
            selection = search.run(seeds, budget=config["budget"], propose=proposer)
        print(json.dumps(selection, indent=2))
    else:
        def evaluate_holdout(policy, contract):
            if (contract["implementation_hash"] != implementation_hash()
                    or contract["nautilus_version"] != nautilus_trader.__version__
                    or contract["python_version"] != sys.version):
                raise ValueError("frozen implementation or runtime changed")
            config = contract["config"]
            validate_config(config)
            catalog = make_catalog()
            iid = InstrumentId.from_str(config["instrument_id"])
            instrument, instrument_source = resolve_instrument(catalog, iid)
            if (instrument_source != contract["instrument_source"]
                    or fingerprint(type(instrument).to_dict(instrument)) != contract["instrument_hash"]):
                raise ValueError("instrument metadata changed")
            fold = Fold(**config["holdout"])
            loaded = [(fold, *load_fold(catalog, iid, fold, config["max_events"]))]
            return {"data_hash": loaded[0][3], "results": evaluator(config, instrument, loaded)(policy)}
        print(json.dumps(finalize(args.run, expected_contract_hash=args.contract_hash,
                                  evaluate_holdout=evaluate_holdout), indent=2))


if __name__ == "__main__":
    main()
