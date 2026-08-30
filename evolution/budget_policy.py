from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class BudgetStage(StrEnum):
    LIFECYCLE = "lifecycle"
    SEARCH_SMOKE = "search_smoke"
    VIABILITY = "viability"
    EXTENDED = "extended"


@dataclass(frozen=True)
class BudgetStageDefinition:
    name: BudgetStage
    minimum_iterations: int
    maximum_iterations: int


BUDGET_POLICY_NAME = "milestone2-search-policy-v1"
BUDGET_STAGES = (
    BudgetStageDefinition(BudgetStage.LIFECYCLE, 10, 10),
    BudgetStageDefinition(BudgetStage.SEARCH_SMOKE, 30, 30),
    BudgetStageDefinition(BudgetStage.VIABILITY, 50, 100),
    BudgetStageDefinition(BudgetStage.EXTENDED, 300, 300),
)


def budget_stage_for_iterations(iterations: int) -> BudgetStage:
    for definition in BUDGET_STAGES:
        if definition.minimum_iterations <= iterations <= definition.maximum_iterations:
            return definition.name
    raise ValueError(
        "unsupported evolution iteration budget; use 10, 30, 50-100, or 300"
    )


def validate_budget(
    iterations: int,
    stage: str | BudgetStage | None = None,
    advancement_record: Path | None = None,
) -> BudgetStage:
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    inferred = budget_stage_for_iterations(iterations)
    if stage is not None:
        try:
            selected = BudgetStage(stage)
        except ValueError as exc:
            raise ValueError(f"unsupported budget stage: {stage}") from exc
        if selected != inferred:
            raise ValueError(
                f"budget stage {selected.value} does not accept {iterations} iterations"
            )
    else:
        selected = inferred

    if selected is BudgetStage.EXTENDED:
        if advancement_record is None:
            raise ValueError("extended budget requires a machine-readable advancement record")
        validate_advancement_record(advancement_record)
    return selected


def validate_advancement_record(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"advancement record not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"advancement record is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("advancement record must be a JSON object")
    if payload.get("policy") != BUDGET_POLICY_NAME:
        raise ValueError("advancement record has an unsupported budget policy")
    if payload.get("target_stage") != BudgetStage.EXTENDED.value:
        raise ValueError("advancement record must target the extended stage")
    if payload.get("approved") is not True:
        raise ValueError("advancement record must set approved to true")
    return payload


def budget_metadata(
    iterations: int,
    random_seed: int,
    stage: str | BudgetStage | None = None,
) -> dict[str, Any]:
    selected = budget_stage_for_iterations(iterations) if stage is None else BudgetStage(stage)
    if selected != budget_stage_for_iterations(iterations):
        raise ValueError(f"budget stage {selected.value} does not accept {iterations} iterations")
    return {
        "policy": BUDGET_POLICY_NAME,
        "budget_stage": selected.value,
        "iterations": iterations,
        "random_seed": random_seed,
    }
