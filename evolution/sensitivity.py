from __future__ import annotations

import json
from pathlib import Path

from evolution.backtest import BacktestResult
from evolution.backtest import run_candidate
from evolution.diagnostic import BASELINES
from evolution.diagnostic import _candidate_payload
from evolution.diagnostic import discovery_split
from evolution.sandbox_worker import load_split
from evolution.spec import DISCOVERY_FOLDS


DEFAULT_FEES_BPS = (0, 5, 10, 15)
DEFAULT_DELAYS_SECONDS = (0, 1, 5)
OFFICIAL_FEE_BPS = 10
OFFICIAL_DELAY_SECONDS = 1


def run_sensitivity(
    instrument_id: str,
    dataset_root: Path,
    run_directory: Path,
    output_path: Path,
    fees_bps: tuple[int, ...] = DEFAULT_FEES_BPS,
    delays_seconds: tuple[int, ...] = DEFAULT_DELAYS_SECONDS,
    include_baselines: bool = True,
) -> dict[str, object]:
    rerank = json.loads((run_directory / "rerank.json").read_text(encoding="utf-8"))
    if not rerank.get("discovery_only"):
        raise ValueError("sensitivity requires a discovery-only rerank")
    champion = rerank["candidates"][0]
    programs = {"executable_champion": _candidate_path(run_directory, champion)}
    if include_baselines:
        programs = {
            "flat": BASELINES["flat"],
            "buy_and_hold": BASELINES["buy_and_hold"],
            "initial_program": BASELINES["initial_program"],
            **programs,
        }
    data = []
    for window in DISCOVERY_FOLDS:
        path, manifest = discovery_split(dataset_root, window.name, instrument_id)
        if manifest.execution_profile != "executable":
            raise ValueError("sensitivity requires executable discovery data")
        data.append(load_split(path, instrument_id))

    results = {}
    for name, program_path in programs.items():
        scenarios = []
        for delay in delays_seconds:
            for fee_bps in fees_bps:
                folds: list[BacktestResult] = []
                for states, quotes, bars in data:
                    folds.append(run_candidate(
                        program_path,
                        instrument_id,
                        states,
                        execution_delay_seconds=delay,
                        quotes=quotes,
                        bars=bars,
                        fee_rate=fee_bps / 10_000,
                    ))
                report = _candidate_payload(folds)
                scenarios.append({
                    "fee_bps": fee_bps,
                    "delay_seconds": delay,
                    "metrics": report,
                })
        results[name] = {
            "program_path": str(program_path),
            "scenarios": scenarios,
            "labels": sensitivity_labels(scenarios),
        }
    official = _scenario(results["executable_champion"]["scenarios"], OFFICIAL_FEE_BPS, OFFICIAL_DELAY_SECONDS)
    expected = champion["executable"]["aggregate"]
    if official["metrics"]["aggregate"] != expected:
        raise RuntimeError("official sensitivity scenario does not match executable rerank")
    payload: dict[str, object] = {
        "instrument_id": instrument_id,
        "discovery_only": True,
        "official_profile": {"fee_bps": OFFICIAL_FEE_BPS, "delay_seconds": OFFICIAL_DELAY_SECONDS},
        "candidate_id": champion["candidate_id"],
        "programs": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def sensitivity_labels(scenarios: list[dict[str, object]]) -> list[str]:
    official = _scenario(scenarios, OFFICIAL_FEE_BPS, OFFICIAL_DELAY_SECONDS)
    zero_fee = _scenario(scenarios, 0, OFFICIAL_DELAY_SECONDS)
    delayed = _scenario(scenarios, OFFICIAL_FEE_BPS, 5)
    official_sharpe = float(official["metrics"]["aggregate"]["net_sharpe"])
    zero_fee_sharpe = float(zero_fee["metrics"]["aggregate"]["net_sharpe"])
    delayed_sharpe = float(delayed["metrics"]["aggregate"]["net_sharpe"])
    labels = []
    if zero_fee_sharpe > 0 >= official_sharpe:
        labels.append("cost_fragile")
    elif official_sharpe > 0:
        labels.append("cost_robust" if delayed_sharpe > 0 else "delay_fragile")
    else:
        labels.append("economically_rejected")
    if official_sharpe <= 0 and delayed_sharpe < official_sharpe:
        labels.append("delay_sensitive")
    return labels


def _candidate_path(run_directory: Path, entry: dict[str, object]) -> Path:
    path = Path(str(entry["program_path"]))
    if not path.is_file():
        path = run_directory / "top_candidates" / path.name
    return path


def _scenario(scenarios: list[dict[str, object]], fee_bps: int, delay_seconds: int):
    return next(
        scenario for scenario in scenarios
        if scenario["fee_bps"] == fee_bps and scenario["delay_seconds"] == delay_seconds
    )
