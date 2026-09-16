"""Immutable run metadata and candidate validation context."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from evolution.candidate import ValidationResult
from evolution.candidate import validate_candidate_file
from evolution.families import sha256_file
from evolution.spec import LEGACY_EXECUTION_CONTRACT
from evolution.spec import validate_execution_contract


@dataclass(frozen=True)
class RunValidationContext:
    reference_path: Path
    expected_family_id: str | None
    execution_contract: str = LEGACY_EXECUTION_CONTRACT


def run_validation_context(run_directory: Path) -> RunValidationContext:
    """Resolve the trusted reference and family from immutable run metadata.

    A family run owns a copied seed reference in its workspace. Runs without a
    family id are legacy runs and use the legacy repository reference.
    """
    metadata_path = run_directory / "run_metadata.json"
    legacy_metadata_path = run_directory / "run-metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    elif legacy_metadata_path.exists():
        metadata = json.loads(legacy_metadata_path.read_text(encoding="utf-8"))
    else:
        # Runs predating family metadata are legacy runs and intentionally use
        # the repository's legacy reference.
        return RunValidationContext(
            Path(__file__).with_name("initial_program.py").resolve(),
            None,
            LEGACY_EXECUTION_CONTRACT,
        )
    if not isinstance(metadata, dict):
        raise ValueError("run metadata must be a mapping")

    family_id = metadata.get("family_id") or None
    execution_contract = str(metadata.get("execution_contract", LEGACY_EXECUTION_CONTRACT))
    validate_execution_contract(execution_contract)
    if family_id is None:
        reference_path = Path(__file__).with_name("initial_program.py").resolve()
    else:
        reference_path = (run_directory / "initial_program.py").resolve()
        if not reference_path.is_file():
            raise ValueError(f"family reference is missing: {reference_path}")
        expected_hash = metadata.get("seed_program_sha256")
        if expected_hash and sha256_file(reference_path) != expected_hash:
            raise ValueError("family reference does not match immutable run metadata")
    return RunValidationContext(
        reference_path,
        str(family_id) if family_id is not None else None,
        execution_contract,
    )

def validate_candidate_in_context(
    context: RunValidationContext,
    candidate_path: Path,
) -> ValidationResult:
    return validate_candidate_file(
        candidate_path,
        context.reference_path,
        context.expected_family_id,
    )


def validate_run_candidate(
    run_directory: Path,
    candidate_path: Path,
) -> ValidationResult:
    return validate_candidate_in_context(
        run_validation_context(run_directory),
        candidate_path,
    )
