from __future__ import annotations

import json
import statistics
from dataclasses import asdict
from pathlib import Path

from evolution.backtest import BacktestResult
from evolution.backtest import run_candidate
from evolution.dataset import verify_manifest
from evolution.metrics import annualized_sharpe
from evolution.sandbox_worker import load_split
from evolution.spec import DISCOVERY_FOLDS
from evolution.spec import STARTING_BALANCE_USDT


BASELINES = {
    "flat": Path(__file__).with_name("baselines") / "flat.py",
    "buy_and_hold": Path(__file__).with_name("baselines") / "buy_and_hold.py",
    "sma_3_8": Path(__file__).with_name("baselines") / "sma_3_8.py",
    "initial_program": Path(__file__).with_name("initial_program.py"),
}


def run_discovery_diagnostic(
    instrument_id: str,
    dataset_root: Path,
    output_path: Path,
) -> dict[str, object]:
    split_data = []
    for window in DISCOVERY_FOLDS:
        split_root, manifest = discovery_split(dataset_root, window.name, instrument_id)
        states, quotes, bars = load_split(split_root, instrument_id)
        split_data.append((manifest, states, quotes, bars))
    results: dict[str, object] = {}
    for name, program_path in BASELINES.items():
        folds = [
            run_candidate(
                program_path,
                instrument_id,
                states,
                execution_delay_seconds=manifest.execution_delay_seconds,
                quotes=quotes,
                bars=bars,
            )
            for manifest, states, quotes, bars in split_data
        ]
        results[name] = _candidate_payload(folds)
    payload: dict[str, object] = {
        "instrument_id": instrument_id,
        "splits": [window.name for window in DISCOVERY_FOLDS],
        "discovery_only": True,
        "baselines": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def discovery_split_path(dataset_root: Path, split: str, instrument_id: str) -> Path:
    return discovery_split(dataset_root, split, instrument_id)[0]


def discovery_split(dataset_root: Path, split: str, instrument_id: str):
    allowed = {window.name for window in DISCOVERY_FOLDS}
    if split not in allowed:
        raise ValueError(f"diagnostics may read discovery folds only: {split}")
    path = dataset_root / split / instrument_id
    manifest = verify_manifest(path / "manifest.json", instrument_id, split)
    return path, manifest


def _candidate_payload(folds: list[BacktestResult]) -> dict[str, object]:
    diagnostics = [fold.diagnostics for fold in folds]
    metrics = [fold.metrics for fold in folds]
    daily_net = tuple(value for fold in metrics for value in fold.daily_returns)
    daily_gross = tuple(value for fold in diagnostics for value in fold.daily_gross_returns)
    closed = sum(fold.closed_positions for fold in metrics)
    total_fee = sum(fold.fee_drag for fold in diagnostics)
    total_gross_pnl = sum(fold.gross_return for fold in diagnostics)
    fold_count = len(folds)
    holding = [value for fold in diagnostics for value in fold.holding_durations_seconds]
    return {
        "aggregate": {
            "gross_return": total_gross_pnl / fold_count,
            "fee_drag": total_fee / fold_count,
            "net_return": sum(fold.net_return for fold in metrics) / fold_count,
            "gross_sharpe": annualized_sharpe(daily_gross),
            "net_sharpe": annualized_sharpe(daily_net),
            "closed_positions": closed,
            "orders": sum(fold.orders for fold in metrics),
            "turnover": sum(fold.turnover for fold in diagnostics) / fold_count,
            "exposure_ratio": statistics.median(fold.exposure_ratio for fold in metrics),
            "average_holding_seconds": statistics.mean(holding) if holding else None,
            "median_holding_seconds": statistics.median(holding) if holding else None,
            "average_gross_pnl_per_position": total_gross_pnl * STARTING_BALANCE_USDT / closed
            if closed else None,
            "average_fee_per_position": total_fee * STARTING_BALANCE_USDT / closed if closed else None,
            "best_daily_net_return": max(daily_net, default=None),
            "worst_daily_net_return": min(daily_net, default=None),
        },
        "folds": [
            {
                "fold": window.name,
                "metrics": asdict(result.metrics),
                "diagnostics": asdict(result.diagnostics),
            }
            for window, result in zip(DISCOVERY_FOLDS, folds, strict=True)
        ],
    }
