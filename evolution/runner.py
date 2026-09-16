from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
import uuid
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
from evolution.lifecycle_summary import _classify_events
from evolution.lifecycle_summary import _load_programs
from evolution.lifecycle_summary import summarize_lifecycle
from evolution.sandbox import DEFAULT_IMAGE
from evolution.sandbox import preflight_sandbox
from evolution.spec import LEGACY_EXECUTION_CONTRACT
from evolution.spec import TRUSTED_INTRADAY_EXECUTION_CONTRACT
from evolution.spec import run_directory
from evolution.spec import validate_execution_contract
from data.nautilus_catalog import _load_dotenv


@dataclass(frozen=True)
class EvolutionRunResult:
    returncode: int
    output_directory: Path
    checkpoint: Path | None
    resume_command: str | None
    rate_limited: bool
    process_returncode: int | None = None


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
    iterations: int | None = None,
    checkpoint: Path | None = None,
    family: EvolutionFamily | str | None = None,
    random_seed: int | None = None,
    budget_stage: str | None = None,
    advancement_record: Path | None = None,
    execution_contract: str | None = None,
) -> EvolutionRunResult:
    if execution_contract is not None:
        validate_execution_contract(execution_contract)
    if isinstance(family, str):
        family = get_family(family)
    if family is not None:
        validate_family_instrument(family.family_id, instrument_id)
    _load_dotenv()
    base_config = load_base_config()
    run_dir = run_directory(output_root, instrument_id, run_id)
    is_resume = checkpoint is not None
    if not is_resume and run_dir.exists():
        raise FileExistsError(f"fresh evolution run already exists: {run_dir}")

    existing_metadata = _read_run_metadata(run_dir) if is_resume else None
    if execution_contract is None:
        execution_contract = (
            str(existing_metadata.get("execution_contract", LEGACY_EXECUTION_CONTRACT))
            if existing_metadata is not None else LEGACY_EXECUTION_CONTRACT
        )
    validate_execution_contract(execution_contract)
    if execution_contract == TRUSTED_INTRADAY_EXECUTION_CONTRACT and family is None:
        raise ValueError("trusted execution contract requires a registered evolution family")
    execution_state = _read_execution_state(run_dir, instrument_id, run_id) if is_resume else None
    if is_resume and iterations is None:
        if execution_state is None:
            raise RuntimeError(f"execution state is missing; cannot safely resume: {run_dir}")
        iterations = int(execution_state["approved_target_iterations"])
    if not is_resume and iterations is None:
        iterations = 30
    if iterations is None:
        raise ValueError("iterations is required for a fresh evolution run")
    if is_resume and random_seed is None and existing_metadata and "random_seed" in existing_metadata:
        random_seed = int(existing_metadata["random_seed"])
    seed = int(base_config["random_seed"]) if random_seed is None else random_seed
    if is_resume and advancement_record is None:
        saved_record = (execution_state or {}).get("advancement_record") or (existing_metadata or {}).get("advancement_record")
        if saved_record:
            advancement_record = Path(str(saved_record))
    selected_stage = validate_budget(iterations, budget_stage, advancement_record)
    dataset_identity = _dataset_identity(dataset_root, instrument_id)
    image = os.environ.get("EVOLUTION_SANDBOX_IMAGE", DEFAULT_IMAGE)

    if is_resume:
        checkpoint, checkpoint_iteration = _validate_resume_inputs(
            run_dir, checkpoint, instrument_id, run_id, family, seed, dataset_identity, execution_contract,
        )
        if checkpoint_iteration >= iterations:
            return EvolutionRunResult(0, run_dir, checkpoint, None, False)
        config_path = run_dir / "openevolve.yaml"
        if not config_path.is_file():
            raise RuntimeError(f"run configuration is missing: {config_path}")
        program_path = (
            run_dir / "initial_program.py"
            if family is not None
            else Path(__file__).parent / "initial_program.py"
        )
        if family is not None and not program_path.is_file():
            raise RuntimeError(f"family seed snapshot is missing: {program_path}")
        _require_runtime_and_preflight(dataset_root, instrument_id, image)
        _record_execution_attempt(run_dir, iterations, selected_stage, advancement_record, checkpoint_iteration)
        upstream_iterations = iterations - checkpoint_iteration
    else:
        missing = [
            dataset_root / f"discovery_{fold}" / instrument_id / "manifest.json"
            for fold in range(1, 6)
            if not (dataset_root / f"discovery_{fold}" / instrument_id / "manifest.json").exists()
        ]
        if missing:
            raise RuntimeError(f"Discovery dataset is missing: {missing[0]}")
        # Perform all external checks before creating the fresh run snapshot.
        _require_runtime_and_preflight(dataset_root, instrument_id, image)
        config_path, run_dir = write_run_config(
            output_root,
            instrument_id,
            run_id,
            iterations,
            family=family,
            random_seed=seed,
            budget_stage=selected_stage,
            advancement_record=advancement_record,
            dataset_root=dataset_root,
            execution_contract=execution_contract,
        )
        program_path = Path(__file__).parent / "initial_program.py"
        if family is not None:
            program_path = run_dir / "initial_program.py"
            shutil.copyfile(family.seed_program, program_path)
            _write_family_metadata(run_dir, family, instrument_id, program_path)
        upstream_iterations = iterations

    # OpenAI's client requires a nonempty key even for an unauthenticated vLLM.
    api_key = os.environ.get("VLLM_API_KEY") or "unused"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PYTHONPATH": str(Path(__file__).parents[1].resolve()),
        "VLLM_API_KEY": api_key,
        "EVOLUTION_INSTRUMENT_ID": instrument_id,
        "EVOLUTION_DATASET_ROOT": str(dataset_root.resolve()),
        "EVOLUTION_SANDBOX_IMAGE": image,
        "EVOLUTION_SANDBOX_TIMEOUT": os.environ.get("EVOLUTION_SANDBOX_TIMEOUT", "300"),
        "EVOLUTION_FAMILY_ID": family.family_id if family is not None else "",
        "EVOLUTION_EXECUTION_CONTRACT": execution_contract,
        "EVOLUTION_REFERENCE_PROGRAM": str(program_path.resolve()),
    }
    command = evolution_command(config_path, run_dir, upstream_iterations, checkpoint, program_path)
    completed, output, _attempt_log = _run_streaming(command, run_dir, env, api_key)
    latest = latest_checkpoint(run_dir)
    if latest is not None:
        export_top_candidates(latest, run_dir)
    summarize_lifecycle(run_dir)
    events = _classify_events([output], _load_programs(run_dir))
    completed_candidates = sum(event["category"] == "accepted_candidate" for event in events)
    terminal_errors = any(
        event["category"] in {
            "provider_http_error", "provider_timeout", "infrastructure_error",
            "unknown_candidate", "unclassified_failure",
        }
        for event in events
    )
    workflow_returncode = completed.returncode or int(completed_candidates == 0 or terminal_errors)
    limited = _contains_rate_limit_signal(output)
    outcome = {
        "process_returncode": completed.returncode,
        "workflow_returncode": workflow_returncode,
        "target_iterations": iterations,
        "submitted_iterations": upstream_iterations,
        "observed_iterations": len(events),
        "accepted_iterations": completed_candidates,
        "rate_limited": limited,
        "attempt_log": str(_attempt_log),
        "events": events,
    }
    (run_dir / "run-outcome.json").write_text(
        json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    resume = resume_command(
        instrument_id,
        dataset_root,
        output_root,
        run_id,
        iterations,
        latest,
        random_seed=seed,
        family_id=family.family_id if family is not None else None,
        advancement_record=advancement_record,
        execution_contract=execution_contract,
    ) if latest and iterations > _checkpoint_iteration(latest) else None
    return EvolutionRunResult(
        workflow_returncode,
        run_dir,
        latest,
        resume,
        limited,
        process_returncode=completed.returncode,
    )


def _require_runtime_and_preflight(dataset_root: Path, instrument_id: str, image: str) -> None:
    preflight_sandbox(dataset_root, instrument_id, image)


def _read_run_metadata(run_dir: Path) -> dict[str, object]:
    paths = (run_dir / "run_metadata.json", run_dir / "run-metadata.json")
    path = next((candidate for candidate in paths if candidate.is_file()), None)
    if path is None:
        raise RuntimeError(f"run metadata is missing; cannot safely resume: {run_dir}")
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"run metadata is unreadable; cannot safely resume: {path}") from exc
    if not isinstance(metadata, dict):
        raise RuntimeError(f"run metadata must be a JSON object: {path}")
    return metadata


def _dataset_identity(dataset_root: Path, instrument_id: str) -> dict[str, object]:
    manifests = {}
    for fold in range(1, 6):
        path = dataset_root / f"discovery_{fold}" / instrument_id / "manifest.json"
        if not path.is_file():
            raise RuntimeError(f"Discovery dataset is missing: {path}")
        manifests[f"discovery_{fold}"] = sha256_file(path)
    return {"root": str(dataset_root.resolve()), "manifests": manifests}


def _validate_resume_inputs(
    run_dir: Path,
    checkpoint: Path,
    instrument_id: str,
    run_id: str,
    family: EvolutionFamily | None,
    seed: int,
    dataset_identity: dict[str, object],
    execution_contract: str,
) -> tuple[Path, int]:
    metadata = _read_run_metadata(run_dir)
    checkpoint = checkpoint.resolve()
    if checkpoint.parent != (run_dir / "checkpoints").resolve():
        raise RuntimeError(f"checkpoint must belong to this run's checkpoint directory: {checkpoint}")
    metadata_path = checkpoint / "metadata.json"
    if not metadata_path.is_file():
        raise RuntimeError(f"checkpoint metadata is missing: {metadata_path}")
    try:
        checkpoint_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        last_iteration = int(checkpoint_metadata["last_iteration"])
        directory_iteration = _checkpoint_iteration(checkpoint)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"checkpoint metadata has no valid last_iteration: {metadata_path}") from exc
    if last_iteration < 0 or directory_iteration != last_iteration:
        raise RuntimeError(f"checkpoint iteration does not match metadata: {checkpoint}")
    if metadata.get("instrument_id") != instrument_id:
        raise RuntimeError("resume instrument_id does not match immutable run metadata")
    if metadata.get("run_id") != run_id:
        raise RuntimeError("resume run_id does not match immutable run metadata")
    if "random_seed" not in metadata:
        raise RuntimeError("run metadata has no immutable random_seed; legacy resume is unverifiable")
    if int(metadata["random_seed"]) != seed:
        raise RuntimeError("resume random seed does not match immutable run metadata")
    requested_family = family.family_id if family is not None else None
    if metadata.get("family_id") != requested_family:
        raise RuntimeError("resume family_id does not match immutable run metadata")
    if metadata.get("dataset_identity") != dataset_identity:
        raise RuntimeError("resume dataset identity does not match immutable run metadata")
    if metadata.get("execution_contract", LEGACY_EXECUTION_CONTRACT) != execution_contract:
        raise RuntimeError("resume execution contract does not match immutable run metadata")
    reference = run_dir / "initial_program.py" if family is not None else Path(__file__).parent / "initial_program.py"
    if not reference.is_file() or metadata.get("seed_program_sha256") != sha256_file(reference):
        raise RuntimeError("resume seed program does not match immutable run metadata")
    snapshot = run_dir / "config.redacted.json"
    try:
        prompt_dir = Path(json.loads(snapshot.read_text(encoding="utf-8"))["prompt"]["template_dir"])
        prompt_hash = composed_prompt_sha256(
            (prompt_dir / "system_message.txt").read_text(encoding="utf-8"),
            (prompt_dir / "diff_user.txt").read_text(encoding="utf-8"),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("resume prompt snapshot is missing or unreadable") from exc
    if metadata.get("composed_prompt_sha256") != prompt_hash:
        raise RuntimeError("resume prompt snapshot does not match immutable run metadata")
    config_path = run_dir / "openevolve.yaml"
    if not config_path.is_file() or metadata.get("config_sha256") != sha256_file(config_path):
        raise RuntimeError("resume OpenEvolve config does not match immutable run metadata")
    return checkpoint, last_iteration


def _read_execution_state(
    run_dir: Path, expected_instrument_id: str | None = None, expected_run_id: str | None = None,
) -> dict[str, object]:
    path = run_dir / "execution-state.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"execution state is missing or unreadable: {path}") from exc
    if not isinstance(state, dict):
        raise RuntimeError(f"execution state must be a JSON object: {path}")
    required = ("run_id", "instrument_id", "approved_target_iterations", "budget_stage")
    if any(key not in state for key in required):
        raise RuntimeError(f"execution state is incomplete: {path}")
    if state["run_id"] != run_dir.name:
        raise RuntimeError("execution state run_id does not match run directory")
    if expected_run_id is not None and state["run_id"] != expected_run_id:
        raise RuntimeError("execution state run_id does not match run")
    if expected_instrument_id is not None and state.get("instrument_id") != expected_instrument_id:
        raise RuntimeError("execution state instrument_id does not match run")
    if not isinstance(state["approved_target_iterations"], int):
        raise RuntimeError("execution state approved target must be an integer")
    validate_budget(
        state["approved_target_iterations"],
        str(state["budget_stage"]),
        Path(state["advancement_record"]) if state.get("advancement_record") else None,
    )
    return state


def _record_execution_attempt(
    run_dir: Path,
    target_iterations: int,
    budget_stage: object,
    advancement_record: Path | None,
    checkpoint_iteration: int,
) -> None:
    path = run_dir / "execution-state.json"
    state = _read_execution_state(run_dir)
    state["approved_target_iterations"] = target_iterations
    state["target_iterations"] = target_iterations
    state["budget_stage"] = str(budget_stage)
    state["advancement_record"] = str(advancement_record.resolve()) if advancement_record else None
    attempts = state.setdefault("attempts", [])
    if not isinstance(attempts, list):
        raise RuntimeError("execution state attempts must be a list")
    attempts.append({
        "target_iterations": target_iterations,
        "budget_stage": str(budget_stage),
        "advancement_record": state["advancement_record"],
        "checkpoint_iteration": checkpoint_iteration,
    })
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _checkpoint_iteration(checkpoint: Path) -> int:
    return int(checkpoint.name.rsplit("_", 1)[-1])


def _run_streaming(
    command: list[str], run_dir: Path, env: dict[str, str], secret: str,
) -> tuple[subprocess.CompletedProcess[str], str, Path]:
    logs = run_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    attempt_log = logs / f"attempt-{time.time_ns()}-{uuid.uuid4().hex}.log"
    chunks: list[str] = []
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command, cwd=Path(__file__).parents[1], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            bufsize=1, start_new_session=True,
        )
        assert process.stdout is not None
        with attempt_log.open("w", encoding="utf-8") as log:
            for line in process.stdout:
                sanitized = _redact_text(line, secret)
                chunks.append(sanitized)
                print(sanitized, end="", flush=True)
                log.write(sanitized)
                log.flush()
        returncode = process.wait()
    except KeyboardInterrupt:
        if process is not None:
            _terminate_process_group(process)
        with attempt_log.open("a", encoding="utf-8") as log:
            log.write("\n[runner] interrupted\n")
        returncode = 130
    output = "".join(chunks)
    with (run_dir / "runner.log").open("a", encoding="utf-8") as log:
        log.write(output)
        if returncode == 130:
            log.write("\n[runner] interrupted\n")
    return subprocess.CompletedProcess(command, returncode, output, ""), output, attempt_log


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def latest_checkpoint(run_dir: Path) -> Path | None:
    checkpoints = run_dir / "checkpoints"
    if not checkpoints.exists():
        return None
    candidates = [path for path in checkpoints.glob("checkpoint_*")
                  if path.is_dir() and path.name.removeprefix("checkpoint_").isdigit()]
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
    execution_contract: str | None = None,
) -> str:
    args = [
        "uv", "run", "python", "-m", "evolution", "resume",
        "--instrument-id", str(instrument_id), "--dataset-root", str(dataset_root),
        "--output-root", str(output_root), "--run-id", str(run_id),
        "--iterations", str(iterations), "--checkpoint", str(checkpoint),
    ]
    if random_seed is not None:
        args.extend(["--seed", str(random_seed)])
    if advancement_record:
        args.extend(["--advancement-record", str(advancement_record)])
    if family_id:
        args.extend(["--family-id", family_id])
    if execution_contract:
        args.extend(["--execution-contract", execution_contract])
    return " ".join(shlex.quote(arg) for arg in args)


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


_RATE_LIMIT_PATTERNS = (
    re.compile(r"\bHTTP(?:/\d(?:\.\d)?)?\s*429\b", re.IGNORECASE),
    re.compile(r"\b(?:status|status_code|error code|response code|http status)\D{0,8}429\b", re.IGNORECASE),
    re.compile(r"\b429\b\s*(?:quota|rate[- ]?limit|retry|retries|too many|exhausted)\b", re.IGNORECASE),
    re.compile(r"\b(?:rate[- ]?limit(?:ed|ing)?|quota(?: exceeded| exhausted)?)\b", re.IGNORECASE),
)


def _contains_rate_limit_signal(value: str) -> bool:
    """Classify provider rate limiting without treating arbitrary log numbers as 429s."""
    return any(pattern.search(value) for pattern in _RATE_LIMIT_PATTERNS)


def _redact_text(value: str, secret: str) -> str:
    return value.replace(secret, "[REDACTED]") if secret else value
