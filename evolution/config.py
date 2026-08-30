from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from evolution.spec import run_directory


BASE_CONFIG = Path(__file__).parent / "configs" / "base.yaml"
SECRET_NAMES = {"api_key", "access_key", "secret_key", "password", "token"}


def load_base_config() -> dict[str, Any]:
    value = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("OpenEvolve base config must be a mapping")
    return value


def write_run_config(
    output_root: Path,
    instrument_id: str,
    run_id: str,
    iterations: int,
) -> tuple[Path, Path]:
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    run_dir = run_directory(output_root, instrument_id, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    config = load_base_config()
    config["max_iterations"] = iterations
    template_dir = Path(config["prompt"]["template_dir"])
    if not template_dir.is_absolute():
        config["prompt"]["template_dir"] = str((Path(__file__).parents[1] / template_dir).resolve())
    config["log_dir"] = str((run_dir / "logs").resolve())
    config["database"]["db_path"] = str((run_dir / "program_database").resolve())
    config["database"]["artifacts_base_path"] = str((run_dir / "artifacts").resolve())
    path = run_dir / "openevolve.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    redacted = redact(config)
    (run_dir / "config.redacted.json").write_text(
        json.dumps(redacted, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path, run_dir


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in SECRET_NAMES else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
