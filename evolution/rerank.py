from __future__ import annotations

import json
from pathlib import Path

from evolution.backtest import BacktestResult
from evolution.diagnostic import BASELINES
from evolution.diagnostic import _candidate_payload
from evolution.diagnostic import discovery_split
from evolution.sandbox_worker import load_split
from evolution.spec import DISCOVERY_FOLDS
from evolution.signatures import behavior_signature_from_payload
from evolution.signatures import source_signature


def rerank_discovery_candidates(
    instrument_id: str,
    fast_dataset_root: Path,
    executable_dataset_root: Path,
    run_directory: Path,
    output_path: Path,
    top_n: int = 10,
    include_baselines: bool = True,
) -> dict[str, object]:
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    candidates = _load_candidates(run_directory, top_n)
    if include_baselines:
        candidates = [
            {"candidate_id": name, "program_path": str(path), "fast_rank": None, "fast_metrics": None}
            for name, path in BASELINES.items()
        ] + candidates
    fast_data = _load_discovery_data(fast_dataset_root, instrument_id, "fast")
    executable_data = _load_discovery_data(executable_dataset_root, instrument_id, "executable")

    results = []
    for candidate in candidates:
        program_path = Path(str(candidate["program_path"]))
        is_evolved_candidate = candidate["fast_rank"] is not None
        fast = _evaluate(program_path, instrument_id, fast_data, run_directory if is_evolved_candidate else None)
        executable = _evaluate(program_path, instrument_id, executable_data, run_directory if is_evolved_candidate else None)
        repeated = _evaluate(program_path, instrument_id, executable_data, run_directory if is_evolved_candidate else None)
        deterministic = executable == repeated
        if not deterministic:
            raise RuntimeError(f"non-deterministic executable rerun: {candidate['candidate_id']}")
        results.append({
            **candidate,
            "source_signature": source_signature(program_path.read_text(encoding="utf-8")),
            "behavior_signature": behavior_signature_from_payload(executable),
            "fast": fast,
            "executable": executable,
            "deterministic": deterministic,
            "comparison": _comparison(fast, executable),
        })

    ranked = sorted(
        results,
        key=lambda item: (
            float(item["executable"]["aggregate"]["net_sharpe"]),
            str(item["candidate_id"]),
        ),
        reverse=True,
    )
    for rank, item in enumerate(ranked, start=1):
        item["executable_rank"] = rank
    candidate_results = [item for item in ranked if item["fast_rank"] is not None]
    for candidate_rank, item in enumerate(candidate_results, start=1):
        item["candidate_executable_rank"] = candidate_rank
    payload: dict[str, object] = {
        "instrument_id": instrument_id,
        "discovery_only": True,
        "fast_profile": {"quote_interval_seconds": 60, "execution_delay_seconds": 0},
        "executable_profile": {"quote_interval_seconds": 1, "execution_delay_seconds": 1},
        "rank_stability": _rank_stability(candidate_results),
        "discovery_summary": _similarity_summary(candidate_results),
        "candidates": ranked,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _load_discovery_data(dataset_root: Path, instrument_id: str, profile: str):
    data = []
    for window in DISCOVERY_FOLDS:
        path, manifest = discovery_split(dataset_root, window.name, instrument_id)
        if manifest.execution_profile != profile:
            raise ValueError(
                f"expected {profile} discovery profile, got {manifest.execution_profile}: {path}",
            )
        states, quotes, bars = load_split(path, instrument_id)
        data.append((manifest.execution_delay_seconds, states, quotes, bars))
    return data


def _evaluate(
    program_path: Path,
    instrument_id: str,
    data,
    run_directory: Path | None = None,
) -> dict[str, object]:
    if run_directory is not None:
        from evolution.run_context import validate_run_candidate

        validation = validate_run_candidate(run_directory, program_path)
        if not validation.valid:
            raise ValueError(
                f"candidate validation failed for {program_path}: "
                + "; ".join(validation.errors),
            )
    from evolution.backtest import run_candidate

    folds: list[BacktestResult] = []
    for delay, states, quotes, bars in data:
        folds.append(run_candidate(
            program_path,
            instrument_id,
            states,
            execution_delay_seconds=delay,
            quotes=quotes,
            bars=bars,
        ))
    return _candidate_payload(folds)


def _load_candidates(run_directory: Path, top_n: int) -> list[dict[str, object]]:
    index_path = run_directory / "top_candidates" / "index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    candidates = []
    for item in payload[:top_n]:
        program_path = Path(str(item["program_path"]))
        if not program_path.is_file():
            program_path = index_path.parent / program_path.name
        candidates.append({
            "candidate_id": str(item["candidate_id"]),
            "program_path": str(program_path),
            "fast_rank": int(item["rank"]),
            "fast_metrics": item.get("metrics"),
        })
    return candidates


def _similarity_summary(candidates: list[dict[str, object]]) -> dict[str, object]:
    groups: dict[str, list[str]] = {}
    behavior_groups: dict[str, list[str]] = {}
    for item in candidates:
        candidate_id = str(item["candidate_id"])
        groups.setdefault(str(item["source_signature"]), []).append(candidate_id)
        behavior_groups.setdefault(str(item["behavior_signature"]), []).append(candidate_id)
    duplicate_groups = [sorted(group) for group in groups.values() if len(group) > 1]
    behavior_duplicate_groups = [sorted(group) for group in behavior_groups.values() if len(group) > 1]
    return {
        "evaluated_count": len(candidates),
        "unique_source_count": len(groups),
        "unique_behavior_count": len(behavior_groups),
        "duplicate_groups": duplicate_groups,
        "behavior_duplicate_groups": behavior_duplicate_groups,
    }


def _rank_stability(candidates: list[dict[str, object]]) -> dict[str, object]:
    if not candidates:
        return {"candidate_count": 0, "spearman": None, "top_3_overlap": 0, "top_10_overlap": 0}
    count = len(candidates)
    differences = sum(
        (int(item["fast_rank"]) - int(item["candidate_executable_rank"])) ** 2
        for item in candidates
    )
    spearman = 1.0 if count == 1 else 1 - 6 * differences / (count * (count * count - 1))
    fast_top_3 = {item["candidate_id"] for item in candidates if int(item["fast_rank"]) <= 3}
    executable_top_3 = {
        item["candidate_id"] for item in candidates if int(item["candidate_executable_rank"]) <= 3
    }
    fast_top_10 = {item["candidate_id"] for item in candidates if int(item["fast_rank"]) <= 10}
    executable_top_10 = {
        item["candidate_id"] for item in candidates if int(item["candidate_executable_rank"]) <= 10
    }
    return {
        "candidate_count": count,
        "spearman": spearman,
        "top_3_overlap": len(fast_top_3 & executable_top_3),
        "top_10_overlap": len(fast_top_10 & executable_top_10),
    }


def _comparison(fast: dict[str, object], executable: dict[str, object]) -> dict[str, object]:
    fast_aggregate = fast["aggregate"]
    executable_aggregate = executable["aggregate"]
    fields = (
        "gross_return",
        "fee_drag",
        "net_return",
        "gross_sharpe",
        "net_sharpe",
        "closed_positions",
        "orders",
        "turnover",
        "exposure_ratio",
        "average_holding_seconds",
    )
    deltas = {}
    for field in fields:
        fast_value = fast_aggregate[field]
        executable_value = executable_aggregate[field]
        deltas[field] = None if fast_value is None or executable_value is None else executable_value - fast_value
    fast_folds = fast["folds"]
    executable_folds = executable["folds"]
    sign_retained = sum(
        (left["metrics"]["net_return"] > 0) == (right["metrics"]["net_return"] > 0)
        for left, right in zip(fast_folds, executable_folds, strict=True)
    )
    return {
        "executable_minus_fast": deltas,
        "fold_return_sign_retained": sign_retained,
        "fold_count": len(fast_folds),
    }
