from __future__ import annotations

from dataclasses import dataclass

from evolution.metrics import AggregateMetrics
from evolution.metrics import FoldMetrics
from evolution.metrics import REJECTED_SCORE
from evolution.metrics import annualized_sharpe


@dataclass(frozen=True)
class CandidateResult:
    candidate_id: str
    discovery: AggregateMetrics
    validation: FoldMetrics | None = None
    holdout: FoldMetrics | None = None


def rank_for_validation(candidates: list[CandidateResult], limit: int = 10) -> list[CandidateResult]:
    eligible = [candidate for candidate in candidates if candidate.discovery.combined_score > REJECTED_SCORE]
    return sorted(
        eligible,
        key=lambda candidate: (
            candidate.discovery.combined_score,
            candidate.candidate_id,
        ),
        reverse=True,
    )[:limit]


def validation_champion(candidates: list[CandidateResult]) -> CandidateResult:
    evaluated = [candidate for candidate in candidates if candidate.validation is not None]
    if not evaluated:
        raise ValueError("no validation results")
    return max(
        evaluated,
        key=lambda candidate: (
            single_fitness(candidate.validation),
            candidate.candidate_id,
        ),
    )


def is_feasible(
    candidate: CandidateResult,
    validation_sma_fitness: float,
    holdout_sma_fitness: float,
    validation_buy_hold_drawdown: float,
    holdout_buy_hold_drawdown: float,
) -> bool:
    validation = candidate.validation
    holdout = candidate.holdout
    if validation is None or holdout is None:
        return False
    return (
        validation.net_return > 0
        and holdout.net_return > 0
        and single_fitness(validation) > validation_sma_fitness
        and single_fitness(holdout) > holdout_sma_fitness
        and validation.max_drawdown <= validation_buy_hold_drawdown
        and holdout.max_drawdown <= holdout_buy_hold_drawdown
        and validation.closed_positions >= 3
        and holdout.closed_positions >= 3
    )


def single_fitness(metrics: FoldMetrics | None) -> float:
    if metrics is None:
        return float("-inf")
    return annualized_sharpe(metrics.daily_returns)
