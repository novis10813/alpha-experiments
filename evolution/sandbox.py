from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


DEFAULT_IMAGE = "alpha-evolution-sandbox:0.1"


@dataclass(frozen=True)
class SandboxResult:
    returncode: int
    payload: dict[str, object] | None
    error: str | None


def docker_command(
    program_path: Path,
    dataset_root: Path,
    instrument_id: str,
    image: str = DEFAULT_IMAGE,
    container_name: str | None = None,
) -> list[str]:
    name = container_name or f"alpha-evolution-{uuid4().hex}"
    command = [
        "docker", "run", "--rm", "--name", name,
        "--network", "none", "--read-only", "--cpus", "1", "--memory", "1g",
        "--pids-limit", "128", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--mount", f"type=bind,src={program_path.resolve()},dst=/candidate/program.py,readonly",
    ]
    for fold in range(1, 6):
        source = (dataset_root / f"discovery_{fold}" / instrument_id).resolve()
        command.extend([
            "--mount",
            f"type=bind,src={source},dst=/dataset/discovery_{fold}/{instrument_id},readonly",
        ])
    command.extend(["--env", f"EVOLUTION_INSTRUMENT_ID={instrument_id}", image])
    return command


def run_sandbox(
    program_path: Path,
    dataset_root: Path,
    instrument_id: str,
    timeout_seconds: int = 300,
    image: str = DEFAULT_IMAGE,
) -> SandboxResult:
    name = f"alpha-evolution-{uuid4().hex}"
    command = docker_command(program_path, dataset_root, instrument_id, image, name)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
        return SandboxResult(124, None, "sandbox timeout")
    if completed.returncode != 0:
        message = _bounded(completed.stderr.strip() or "sandbox exited non-zero")
        if completed.returncode in (137, 143):
            message = "sandbox terminated (possible OOM)"
        return SandboxResult(completed.returncode, None, message)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return SandboxResult(1, None, "sandbox returned invalid JSON")
    if not isinstance(payload, dict):
        return SandboxResult(1, None, "sandbox returned a non-object result")
    return SandboxResult(0, payload, None)


def _bounded(value: str, limit: int = 2000) -> str:
    return value[:limit]
