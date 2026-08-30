from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from evolution.metrics import FoldMetrics
from evolution.metrics import REJECTED_SCORE
from evolution.metrics import annualized_sharpe


class RejectionReason(StrEnum):
    CANDIDATE = "candidate_validation"
    LIFECYCLE = "lifecycle"
    SANDBOX = "sandbox"
    ORDER = "order_rejection"
    INSUFFICIENT_TRADES = "insufficient_closed_positions"
    INSUFFICIENT_ACTIVE_FOLDS = "insufficient_active_folds"
    NON_FINITE_METRICS = "non_finite_metrics"
    ECONOMIC = "economic_rejection"


@dataclass(frozen=True)
class EligibilityPolicy:
    minimum_closed_positions: int = 20
    minimum_active_folds: int = 4


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    score: float
    reasons: tuple[RejectionReason, ...]


DEFAULT_ELIGIBILITY_POLICY = EligibilityPolicy()


def evaluate_eligibility(
    folds: tuple[FoldMetrics, ...],
    policy: EligibilityPolicy = DEFAULT_ELIGIBILITY_POLICY,
) -> EligibilityResult:
    closed = sum(fold.closed_positions for fold in folds)
    active = sum(fold.closed_positions > 0 for fold in folds)
    reasons: list[RejectionReason] = []
    if any(fold.rejected for fold in folds):
        reasons.append(RejectionReason.ORDER)
    if closed < policy.minimum_closed_positions:
        reasons.append(RejectionReason.INSUFFICIENT_TRADES)
    if active < policy.minimum_active_folds:
        reasons.append(RejectionReason.INSUFFICIENT_ACTIVE_FOLDS)
    score = annualized_sharpe(value for fold in folds for value in fold.daily_returns)
    return EligibilityResult(not reasons, score if not reasons else REJECTED_SCORE, tuple(reasons))


def audit_checkpoint_eligibility(
    checkpoint: Path,
    thresholds: tuple[int, ...] = (10, 15, 20, 30),
) -> dict[str, object]:
    programs = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((checkpoint / "programs").glob("*.json"))]
    available = [
        program for program in programs
        if "closed_trades" in program.get("metrics", {}) and "active_folds" in program.get("metrics", {})
    ]
    rows = []
    for threshold in thresholds:
        eligible = sum(
            float(program["metrics"]["closed_trades"]) >= threshold
            and float(program["metrics"]["active_folds"]) >= DEFAULT_ELIGIBILITY_POLICY.minimum_active_folds
            for program in available
        )
        rows.append({"minimum_closed_positions": threshold, "eligible_candidates": eligible})
    fixed_rejections = sum(
        float(program.get("metrics", {}).get("combined_score", REJECTED_SCORE)) <= REJECTED_SCORE
        for program in programs
    )
    return {
        "program_count": len(programs),
        "programs_with_activity_metrics": len(available),
        "fixed_score_rejections": fixed_rejections,
        "thresholds": rows,
        "historical_reason_limit": (
            "checkpoint artifacts do not preserve fold-level reasons for every rejected candidate"
        ),
    }
