from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualificationResult:
    qualified: bool
    candidate_id: str
    reasons: tuple[str, ...]


def qualify_discovery(
    rerank: dict[str, object],
    sensitivity: dict[str, object],
    family_id: str,
) -> QualificationResult:
    reasons: list[str] = []
    candidates = list(rerank.get("candidates", []))
    if not candidates:
        return QualificationResult(False, "", ("missing_executable_candidates",))
    champion = candidates[0]
    candidate_id = str(champion["candidate_id"])
    aggregate = champion["executable"]["aggregate"]
    folds = champion["executable"]["folds"]
    if not family_id:
        reasons.append("missing_family_id")
    if float(aggregate["net_sharpe"]) <= 0:
        reasons.append("non_positive_executable_sharpe")
    fold_returns = [float(fold["metrics"]["net_return"]) for fold in folds]
    ordered = sorted(fold_returns)
    median = ordered[len(ordered) // 2]
    if median <= 0:
        reasons.append("non_positive_median_fold_return")
    active = sum(int(fold["metrics"]["closed_positions"]) > 0 for fold in folds)
    if active < 4:
        reasons.append("insufficient_active_folds")
    if sum(value > 0 for value in fold_returns) < 3:
        reasons.append("insufficient_positive_folds")
    if not champion.get("deterministic"):
        reasons.append("non_deterministic_executable_rerun")
    if sensitivity.get("candidate_id") != candidate_id:
        reasons.append("sensitivity_candidate_mismatch")
    labels = sensitivity.get("programs", {}).get("executable_champion", {}).get("labels", [])
    if "cost_fragile" in labels or "delay_fragile" in labels:
        reasons.append("sensitivity_fragile")
    return QualificationResult(not reasons, candidate_id, tuple(reasons))
