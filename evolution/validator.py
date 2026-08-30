from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from data.orderbook_quotes import QuoteRow
from evolution.ledger import acquire_holdout_lock
from evolution.ledger import complete_holdout
from evolution.ledger import record_validation
from evolution.ledger import register_family
from evolution.market_state import EvolutionMarketState
from evolution.metrics import AggregateMetrics
from evolution.selection import CandidateResult
from evolution.selection import is_feasible
from evolution.selection import single_fitness
from evolution.selection import validation_champion
from evolution.qualification import qualify_discovery
from evolution.report import write_research_report
from evolution.dataset import verify_manifest
from evolution.run_context import run_validation_context
from evolution.run_context import validate_run_candidate
from evolution.spec import ResearchStatus
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog


BUY_AND_HOLD = Path(__file__).parent / "baselines" / "buy_and_hold.py"
SMA_3_8 = Path(__file__).parent / "baselines" / "sma_3_8.py"


def promote_top_candidates(
    instrument_id: str,
    dataset_root: Path,
    run_dir: Path,
    family_id: str,
    hypothesis: str,
    governance_root: Path,
    run_id: str,
) -> dict[str, object]:
    register_family(governance_root, family_id, hypothesis, instrument_id, run_id)
    rerank = json.loads((run_dir / "rerank.json").read_text(encoding="utf-8"))
    sensitivity = json.loads((run_dir / "sensitivity.json").read_text(encoding="utf-8"))
    qualification = qualify_discovery(rerank, sensitivity, family_id)
    if not qualification.qualified:
        payload = {
            "instrument_id": instrument_id,
            "family_id": family_id,
            "status": "infrastructure_only",
            "qualified": False,
            "candidate_id": qualification.candidate_id,
            "reasons": qualification.reasons,
            "validation_accessed": False,
            "holdout_accessed": False,
        }
        (run_dir / "promotion-disqualified.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        return payload
    index = json.loads((run_dir / "top_candidates" / "index.json").read_text(encoding="utf-8"))
    context = run_validation_context(run_dir)
    if context.expected_family_id is not None and context.expected_family_id != family_id:
        raise ValueError(
            f"promotion family {family_id!r} does not match immutable run family "
            f"{context.expected_family_id!r}",
        )
    candidates: list[tuple[dict[str, object], Path, AggregateMetrics]] = []
    for entry in index[:10]:
        path = _candidate_path(run_dir, entry)
        validation = validate_run_candidate(run_dir, path)
        if validation.valid:
            candidates.append((entry, path, _aggregate_from_dict(entry["metrics"])))
    if not candidates:
        payload = {
            "instrument_id": instrument_id,
            "family_id": family_id,
            "status": ResearchStatus.REJECTED.value,
            "qualified": True,
            "candidate_id": qualification.candidate_id,
            "reason": "no_valid_candidates",
            "validation_accessed": False,
            "holdout_accessed": False,
        }
        (run_dir / "promotion-rejected.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        return payload
    from evolution.backtest import run_candidate

    validation_states, validation_quotes, validation_bars = _load_split(dataset_root, "validation", instrument_id)
    record_validation(governance_root, family_id, instrument_id, run_id)
    if not validation_states:
        payload = {
            "instrument_id": instrument_id,
            "family_id": family_id,
            "status": ResearchStatus.INCONCLUSIVE.value,
            "qualified": True,
            "candidate_id": qualification.candidate_id,
            "reason": "empty_validation_pool",
            "validation_accessed": True,
            "holdout_accessed": False,
        }
        (run_dir / "promotion-inconclusive.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        return payload
    evaluated: list[CandidateResult] = []
    paths: dict[str, Path] = {}
    for entry, path, discovery in candidates:
        first = run_candidate(path, instrument_id, validation_states, 1, validation_quotes, validation_bars).metrics
        second = run_candidate(path, instrument_id, validation_states, 1, validation_quotes, validation_bars).metrics
        if first != second:
            continue
        candidate = CandidateResult(entry["candidate_id"], discovery, validation=first)
        evaluated.append(candidate)
        paths[candidate.candidate_id] = path
    if not evaluated:
        payload = {
            "instrument_id": instrument_id,
            "family_id": family_id,
            "status": ResearchStatus.REJECTED.value,
            "qualified": True,
            "candidate_id": qualification.candidate_id,
            "reason": "no_valid_candidates",
            "validation_accessed": True,
            "holdout_accessed": False,
        }
        (run_dir / "promotion-rejected.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        return payload
    champion = validation_champion(evaluated)
    acquire_holdout_lock(governance_root, family_id, instrument_id, run_id, champion.candidate_id)
    holdout_states, holdout_quotes, holdout_bars = _load_split(dataset_root, "holdout", instrument_id)
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
    complete_holdout(governance_root, family_id, instrument_id, run_id, champion.candidate_id)
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


def _candidate_path(run_directory: Path, entry: dict[str, object]) -> Path:
    path = Path(str(entry["program_path"]))
    if not path.is_file():
        path = run_directory / "top_candidates" / path.name
    return path


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
        if candidate.validation.net_return > 0 and candidate.holdout.net_return > 0:
            return "rule_candidate"
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
