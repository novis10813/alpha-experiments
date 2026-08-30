from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from evolution.candidate import validate_candidate_file
from evolution.metrics import REJECTED_SCORE
from evolution.sandbox import run_sandbox
from openevolve.evaluation_result import EvaluationResult


REFERENCE_PATH = Path(__file__).with_name("initial_program.py")


def reference_path() -> Path:
    configured = os.environ.get("EVOLUTION_REFERENCE_PROGRAM")
    return Path(configured) if configured else REFERENCE_PATH


def evaluate(program_path: str) -> EvaluationResult:
    validation = validate_candidate_file(
        program_path,
        reference_path(),
        os.environ.get("EVOLUTION_FAMILY_ID"),
    )
    if not validation.valid:
        return _failure(1, "; ".join(validation.errors), validation.complexity)
    dataset_root = os.environ.get("EVOLUTION_DATASET_ROOT")
    instrument_id = os.environ.get("EVOLUTION_INSTRUMENT_ID")
    if not dataset_root or not instrument_id:
        return _failure(1, "trusted evaluator environment is incomplete", validation.complexity)
    # OpenEvolve creates candidates as mode 0600 temporary files. The sandbox
    # deliberately runs as an unrelated non-root UID, so give Docker a
    # short-lived, world-readable copy instead of weakening the container user.
    with tempfile.TemporaryDirectory(prefix="evolution-sandbox-") as directory:
        staged_program = Path(directory) / "program.py"
        shutil.copyfile(program_path, staged_program)
        staged_program.chmod(0o444)
        sandbox = run_sandbox(
            staged_program,
            Path(dataset_root),
            instrument_id,
            timeout_seconds=int(os.environ.get("EVOLUTION_SANDBOX_TIMEOUT", "300")),
            image=os.environ.get("EVOLUTION_SANDBOX_IMAGE", "alpha-evolution-sandbox:0.1"),
            reference_path=reference_path(),
        )
    if sandbox.error or sandbox.payload is None:
        return _failure(2, sandbox.error or "sandbox failure", validation.complexity)
    if not sandbox.payload.get("ok"):
        return _failure(
            int(sandbox.payload.get("stage", 2)),
            str(sandbox.payload.get("error", "candidate rejected")),
            validation.complexity,
        )
    metrics = {key: float(value) for key, value in dict(sandbox.payload["metrics"]).items()}
    metrics["code_complexity"] = validation.complexity
    artifact = json.dumps(
        {"stage": 3, "summary": metrics},
        sort_keys=True,
        separators=(",", ":"),
    )
    return EvaluationResult(metrics=metrics, artifacts={"evaluation.json": artifact})


def _failure(stage: int, error: str, complexity: float) -> EvaluationResult:
    metrics = {
        "combined_score": REJECTED_SCORE,
        "median_return": -1.0,
        "worst_return": -1.0,
        "median_drawdown": 1.0,
        "median_profit_factor": 0.0,
        "closed_trades": 0.0,
        "orders": 0.0,
        "exposure_ratio": 0.0,
        "active_folds": 0.0,
        "code_complexity": complexity,
    }
    artifact = json.dumps({"stage": stage, "error": error[:2000]}, sort_keys=True)
    return EvaluationResult(metrics=metrics, artifacts={"evaluation.json": artifact})
