from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from data.orderbook_quotes import QuoteRow
from evolution.backtest import run_candidate
from evolution.market_state import EvolutionMarketState
from evolution.metrics import AggregateMetrics
from evolution.selection import CandidateResult
from evolution.selection import is_feasible
from evolution.selection import single_fitness
from evolution.selection import validation_champion
from evolution.report import write_research_report
from evolution.dataset import verify_manifest
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog


BUY_AND_HOLD = Path(__file__).parent / "baselines" / "buy_and_hold.py"
SMA_3_8 = Path(__file__).parent / "baselines" / "sma_3_8.py"


def promote_top_candidates(
    instrument_id: str,
    dataset_root: Path,
    run_dir: Path,
) -> dict[str, object]:
    index = json.loads((run_dir / "top_candidates" / "index.json").read_text(encoding="utf-8"))
    validation_states, validation_quotes, validation_bars = _load_split(dataset_root, "validation", instrument_id)
    evaluated: list[CandidateResult] = []
    paths: dict[str, Path] = {}
    for entry in index[:10]:
        discovery = _aggregate_from_dict(entry["metrics"])
        path = Path(entry["program_path"])
        first = run_candidate(path, instrument_id, validation_states, 1, validation_quotes, validation_bars).metrics
        second = run_candidate(path, instrument_id, validation_states, 1, validation_quotes, validation_bars).metrics
        if first != second:
            continue
        candidate = CandidateResult(entry["candidate_id"], discovery, validation=first)
        evaluated.append(candidate)
        paths[candidate.candidate_id] = path
    champion = validation_champion(evaluated)
    holdout_marker = run_dir / "holdout.lock.json"
    if holdout_marker.exists():
        raise RuntimeError("final holdout has already been consumed for this run")
    holdout_states, holdout_quotes, holdout_bars = _load_split(dataset_root, "holdout", instrument_id)
    holdout_marker.write_text(
        json.dumps({"candidate_id": champion.candidate_id, "status": "started"}) + "\n",
        encoding="utf-8",
    )
    holdout = run_candidate(paths[champion.candidate_id], instrument_id, holdout_states, 1, holdout_quotes, holdout_bars).metrics
    champion = CandidateResult(champion.candidate_id, champion.discovery, champion.validation, holdout)
    validation_sma = run_candidate(SMA_3_8, instrument_id, validation_states, 1, validation_quotes, validation_bars).metrics
    holdout_sma = run_candidate(SMA_3_8, instrument_id, holdout_states, 1, holdout_quotes, holdout_bars).metrics
    validation_bh = run_candidate(BUY_AND_HOLD, instrument_id, validation_states, 1, validation_quotes, validation_bars).metrics
    holdout_bh = run_candidate(BUY_AND_HOLD, instrument_id, holdout_states, 1, holdout_quotes, holdout_bars).metrics
    feasible = is_feasible(
        champion,
        single_fitness(validation_sma),
        single_fitness(holdout_sma),
        validation_bh.max_drawdown,
        holdout_bh.max_drawdown,
    )
    status = "accepted_alpha" if feasible else _research_status(champion)
    payload = {
        "instrument_id": instrument_id,
        "champion": {
            "candidate_id": champion.candidate_id,
            "program_path": str(paths[champion.candidate_id]),
            "discovery": asdict(champion.discovery),
            "validation": asdict(champion.validation),
            "holdout": asdict(champion.holdout),
        },
        "baselines": {
            "validation_sma_3_8": asdict(validation_sma),
            "holdout_sma_3_8": asdict(holdout_sma),
            "validation_buy_and_hold": asdict(validation_bh),
            "holdout_buy_and_hold": asdict(holdout_bh),
        },
        "feasible": feasible,
        "status": status,
    }
    (run_dir / "promotion.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    champion_path = run_dir / "champion.py"
    champion_path.write_text(paths[champion.candidate_id].read_text(encoding="utf-8"), encoding="utf-8")
    write_research_report(
        champion,
        feasible,
        {
            "validation_vs_sma_fitness": single_fitness(champion.validation) - single_fitness(validation_sma),
            "holdout_vs_sma_fitness": single_fitness(champion.holdout) - single_fitness(holdout_sma),
        },
        run_dir,
    )
    holdout_marker.write_text(
        json.dumps({"candidate_id": champion.candidate_id, "status": "completed"}) + "\n",
        encoding="utf-8",
    )
    return payload


def _load_split(dataset_root: Path, split: str, instrument_id: str):
    root = dataset_root / split / instrument_id
    verify_manifest(root / "manifest.json", instrument_id, split)
    catalog = ParquetDataCatalog(root)
    states = [
        item.data
        for item in catalog.query(EvolutionMarketState, identifiers=[instrument_id])
    ]
    ticks = catalog.quote_ticks(instrument_ids=[InstrumentId.from_str(instrument_id)])
    bars = catalog.bars(instrument_ids=[instrument_id])
    quotes = [_quote_row(tick) for tick in ticks]
    return states, quotes, bars


def _aggregate_from_dict(metrics: dict[str, float]) -> AggregateMetrics:
    return AggregateMetrics(
        combined_score=float(metrics["combined_score"]),
        median_return=float(metrics["median_return"]),
        worst_return=float(metrics["worst_return"]),
        median_drawdown=float(metrics["median_drawdown"]),
        median_profit_factor=float(metrics["median_profit_factor"]),
        closed_positions=int(metrics["closed_trades"]),
        orders=int(metrics["orders"]),
        exposure_ratio=float(metrics["exposure_ratio"]),
        active_folds=int(metrics["active_folds"]),
    )


def _research_status(candidate: CandidateResult) -> str:
    if candidate.validation and candidate.holdout:
        if candidate.validation.net_return > 0 or candidate.holdout.net_return > 0:
            return "feature_candidate"
    return "rejected"


def _quote_row(tick) -> QuoteRow:
    bid = float(str(tick.bid_price))
    ask = float(str(tick.ask_price))
    mid = (bid + ask) / 2
    return QuoteRow(
        ts_event=tick.ts_event,
        instrument_id=str(tick.instrument_id),
        bid=bid,
        ask=ask,
        mid=mid,
        spread=ask - bid,
        spread_bps=(ask - bid) / mid * 10_000 if mid else 0.0,
    )
