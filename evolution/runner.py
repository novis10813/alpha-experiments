from __future__ import annotations

import os
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from evolution.budget_policy import validate_budget
from evolution.config import load_base_config
from evolution.config import write_run_config
from evolution.families import EvolutionFamily
from evolution.families import composed_prompt_sha256
from evolution.families import get_family
from evolution.families import sha256_file
from evolution.families import validate_family_instrument
from evolution.metrics import REJECTED_SCORE
from data.nautilus_catalog import _load_dotenv


@dataclass(frozen=True)
class EvolutionRunResult:
    returncode: int
    output_directory: Path
    checkpoint: Path | None
    resume_command: str | None
    rate_limited: bool


def evolution_command(
    config_path: Path,
    output_directory: Path,
    iterations: int,
    checkpoint: Path | None = None,
    program_path: Path | None = None,
) -> list[str]:
    command = [
        "uv", "run", "openevolve-run",
        str((program_path or (Path(__file__).parent / "initial_program.py")).resolve()),
        str((Path(__file__).parent / "evaluator.py").resolve()),
        "--config", str(config_path.resolve()),
        "--output", str(output_directory.resolve()),
        "--iterations", str(iterations),
    ]
    if checkpoint is not None:
        command.extend(["--checkpoint", str(checkpoint.resolve())])
    return command


def run_evolution(
    instrument_id: str,
    dataset_root: Path,
    output_root: Path,
    run_id: str,
    iterations: int = 30,
    checkpoint: Path | None = None,
    family: EvolutionFamily | str | None = None,
    random_seed: int | None = None,
    budget_stage: str | None = None,
    advancement_record: Path | None = None,
) -> EvolutionRunResult:
    if isinstance(family, str):
        family = get_family(family)
    if family is not None:
        validate_family_instrument(family.family_id, instrument_id)
    _load_dotenv()
    seed = int(load_base_config()["random_seed"]) if random_seed is None else random_seed
    selected_stage = validate_budget(iterations, budget_stage, advancement_record)
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("Missing required environment variable: OPENROUTER_API_KEY")
    missing = [
        dataset_root / f"discovery_{fold}" / instrument_id / "manifest.json"
        for fold in range(1, 6)
        if not (dataset_root / f"discovery_{fold}" / instrument_id / "manifest.json").exists()
    ]
    if missing:
        raise RuntimeError(f"Discovery dataset is missing: {missing[0]}")
    config_path, run_dir = write_run_config(
        output_root,
        instrument_id,
        run_id,
        iterations,
        family=family,
        random_seed=seed,
        budget_stage=selected_stage,
        advancement_record=advancement_record,
    )
    program_path = Path(__file__).parent / "initial_program.py"
    if family is not None:
        program_path = run_dir / "initial_program.py"
        shutil.copyfile(family.seed_program, program_path)
        _write_family_metadata(run_dir, family, instrument_id, program_path)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PYTHONPATH": str(Path(__file__).parents[1].resolve()),
        "OPENROUTER_API_KEY": api_key,
        "EVOLUTION_INSTRUMENT_ID": instrument_id,
        "EVOLUTION_DATASET_ROOT": str(dataset_root.resolve()),
        "EVOLUTION_SANDBOX_IMAGE": os.environ.get("EVOLUTION_SANDBOX_IMAGE", "alpha-evolution-sandbox:0.1"),
        "EVOLUTION_SANDBOX_TIMEOUT": os.environ.get("EVOLUTION_SANDBOX_TIMEOUT", "300"),
        "EVOLUTION_FAMILY_ID": family.family_id if family is not None else "",
        "EVOLUTION_REFERENCE_PROGRAM": str(program_path.resolve()),
    }
    completed = subprocess.run(
        evolution_command(config_path, run_dir, iterations, checkpoint, program_path),
        cwd=Path(__file__).parents[1],
        env=env,
        capture_output=True,
        text=True,
    )
    output = _redact_text(completed.stdout + completed.stderr, api_key)
    (run_dir / "runner.log").write_text(output, encoding="utf-8")
    latest = latest_checkpoint(run_dir)
    if latest is not None:
        export_top_candidates(latest, run_dir)
    limited = completed.returncode != 0 and any(
        marker in output.lower() for marker in ("429", "rate limit", "quota")
    )
    resume = resume_command(
        instrument_id,
        dataset_root,
        output_root,
        run_id,
        300,
        latest,
        random_seed=seed,
        family_id=family.family_id if family is not None else None,
        advancement_record=advancement_record,
    ) if latest else None
    return EvolutionRunResult(completed.returncode, run_dir, latest, resume, limited)


def latest_checkpoint(run_dir: Path) -> Path | None:
    checkpoints = run_dir / "checkpoints"
    if not checkpoints.exists():
        return None
    candidates = [path for path in checkpoints.glob("checkpoint_*") if path.is_dir()]
    return max(candidates, key=lambda path: int(path.name.rsplit("_", 1)[-1]), default=None)


def resume_command(
    instrument_id: str,
    dataset_root: Path,
    output_root: Path,
    run_id: str,
    iterations: int,
    checkpoint: Path,
    random_seed: int | None = None,
    family_id: str | None = None,
    advancement_record: Path | None = None,
) -> str:
    command = (
        "uv run python -m evolution resume"
        f" --instrument-id {instrument_id} --dataset-root {dataset_root}"
        f" --output-root {output_root} --run-id {run_id} --iterations {iterations}"
        f" --checkpoint {checkpoint}"
        + (f" --seed {random_seed}" if random_seed is not None else "")
        + (f" --advancement-record {advancement_record}" if advancement_record else "")
    )
    return f"{command} --family-id {family_id}" if family_id else command


def _write_family_metadata(
    run_dir: Path,
    family: EvolutionFamily,
    instrument_id: str,
    program_path: Path,
) -> Path:
    prompt_dir = run_dir / "prompts"
    payload = {
        "family_id": family.family_id,
        "hypothesis": family.hypothesis,
        "instrument_id": instrument_id,
        "seed_program_sha256": sha256_file(program_path),
        "composed_prompt_sha256": composed_prompt_sha256(
            (prompt_dir / "system_message.txt").read_text(encoding="utf-8"),
            (prompt_dir / "diff_user.txt").read_text(encoding="utf-8"),
        ),
    }
    path = run_dir / "run_metadata.json"
    budget_path = run_dir / "run-metadata.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    budget_metadata = json.loads(budget_path.read_text(encoding="utf-8")) if budget_path.exists() else {}
    metadata = {**budget_metadata, **existing}
    for key, value in payload.items():
        if key in existing and existing[key] != value:
            raise RuntimeError("immutable family run metadata does not match")
        if key in metadata and metadata[key] != value:
            raise RuntimeError("immutable family run metadata does not match")
    metadata.update(payload)
    encoded = json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    path.write_text(encoded, encoding="utf-8")
    budget_path.write_text(encoded, encoding="utf-8")
    snapshot = run_dir / "config.redacted.json"
    if snapshot.exists():
        redacted = json.loads(snapshot.read_text(encoding="utf-8"))
        redacted["run_metadata"] = metadata
        snapshot.write_text(json.dumps(redacted, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def export_top_candidates(checkpoint: Path, run_dir: Path, limit: int = 10) -> Path:
    programs = []
    for path in (checkpoint / "programs").glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if float(payload.get("metrics", {}).get("combined_score", REJECTED_SCORE)) <= REJECTED_SCORE:
            continue
        programs.append(payload)
    programs.sort(
        key=lambda payload: (
            float(payload["metrics"].get("combined_score", REJECTED_SCORE)),
            str(payload["id"]),
        ),
        reverse=True,
    )
    target = run_dir / "top_candidates"
    target.mkdir(parents=True, exist_ok=True)
    index = []
    for rank, payload in enumerate(programs[:limit], start=1):
        program_path = target / f"{rank:02d}-{payload['id']}.py"
        program_path.write_text(payload["code"], encoding="utf-8")
        index.append({
            "rank": rank,
            "candidate_id": payload["id"],
            "program_path": str(program_path.resolve()),
            "metrics": payload["metrics"],
        })
    index_path = target / "index.json"
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return index_path


def _redact_text(value: str, secret: str) -> str:
    return value.replace(secret, "[REDACTED]") if secret else value
