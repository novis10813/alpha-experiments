from __future__ import annotations

import json
import os
import re
from datetime import UTC
from datetime import datetime
from pathlib import Path


FAMILY_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_family_id(family_id: str) -> str:
    if not FAMILY_ID_PATTERN.fullmatch(family_id):
        raise ValueError("family_id must use lowercase letters, digits, and single hyphens")
    return family_id


def register_family(
    governance_root: Path,
    family_id: str,
    hypothesis: str,
    instrument_id: str,
    run_id: str,
) -> Path:
    validate_family_id(family_id)
    if not hypothesis.strip():
        raise ValueError("hypothesis cannot be empty")
    path = governance_root / family_id / "ledger.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _read(path) if path.exists() else {
        "family_id": family_id,
        "hypothesis": hypothesis.strip(),
        "instruments": {},
    }
    if payload["hypothesis"] != hypothesis.strip():
        raise ValueError("family hypothesis cannot change after registration")
    record = payload["instruments"].setdefault(instrument_id, {
        "run_ids": [],
        "validation_consumed": False,
        "holdout_consumed": False,
    })
    if run_id not in record["run_ids"]:
        record["run_ids"].append(run_id)
    _atomic_write(path, payload)
    return path


def record_validation(governance_root: Path, family_id: str, instrument_id: str, run_id: str) -> None:
    path = governance_root / validate_family_id(family_id) / "ledger.json"
    payload = _read(path)
    record = payload["instruments"][instrument_id]
    record["validation_consumed"] = True
    record["validation_run_id"] = run_id
    _atomic_write(path, payload)


def acquire_holdout_lock(
    governance_root: Path,
    family_id: str,
    instrument_id: str,
    run_id: str,
    candidate_id: str,
) -> Path:
    family = governance_root / validate_family_id(family_id)
    ledger = _read(family / "ledger.json")
    record = ledger["instruments"][instrument_id]
    if record.get("holdout_consumed"):
        raise RuntimeError("final holdout has already been consumed for this research family")
    path = family / f"holdout-{instrument_id.replace('.', '_').lower()}.lock.json"
    payload = json.dumps({
        "family_id": family_id,
        "instrument_id": instrument_id,
        "run_id": run_id,
        "candidate_id": candidate_id,
        "status": "started",
        "timestamp": datetime.now(UTC).isoformat(),
    }, sort_keys=True) + "\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(payload)
    return path


def complete_holdout(
    governance_root: Path,
    family_id: str,
    instrument_id: str,
    run_id: str,
    candidate_id: str,
) -> None:
    family = governance_root / validate_family_id(family_id)
    path = family / "ledger.json"
    payload = _read(path)
    record = payload["instruments"][instrument_id]
    record.update({
        "holdout_consumed": True,
        "holdout_run_id": run_id,
        "holdout_candidate_id": candidate_id,
    })
    _atomic_write(path, payload)
    lock = family / f"holdout-{instrument_id.replace('.', '_').lower()}.lock.json"
    lock.write_text(json.dumps({
        "family_id": family_id,
        "instrument_id": instrument_id,
        "run_id": run_id,
        "candidate_id": candidate_id,
        "status": "completed",
    }, sort_keys=True) + "\n", encoding="utf-8")


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
