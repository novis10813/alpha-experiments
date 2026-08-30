from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evolution.families import EvolutionFamily

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
    family: EvolutionFamily | None = None,
    random_seed: int | None = None,
    budget_stage: str | None = None,
    advancement_record: Path | None = None,
) -> tuple[Path, Path]:
    from evolution.budget_policy import budget_metadata
    from evolution.budget_policy import validate_budget

    selected_stage = validate_budget(iterations, budget_stage, advancement_record)
    run_dir = run_directory(output_root, instrument_id, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    config = load_base_config()
    seed = config["random_seed"] if random_seed is None else random_seed
    config["max_iterations"] = iterations
    config["random_seed"] = seed
    run_metadata = {
        "schema_version": 1,
        "instrument_id": instrument_id,
        "run_id": run_id,
        **budget_metadata(iterations, seed, selected_stage),
    }
    if advancement_record is not None:
        run_metadata["advancement_record"] = str(advancement_record.resolve())
    template_dir = Path(config["prompt"]["template_dir"])
    if not template_dir.is_absolute():
        template_dir = (Path(__file__).parents[1] / template_dir).resolve()
    if family is not None:
        template_dir = run_dir / "prompts"
        template_dir.mkdir(parents=True, exist_ok=True)
        for name in ("system_message.txt", "diff_user.txt"):
            common = (Path(__file__).parent / "prompts" / name).read_text(encoding="utf-8")
            context = "\n\n# Family context\n" + family.prompt_context + "\n" if name == "system_message.txt" else ""
            (template_dir / name).write_text(common + context, encoding="utf-8")
    config["prompt"]["template_dir"] = str(template_dir.resolve())
    config["log_dir"] = str((run_dir / "logs").resolve())
    config["database"]["db_path"] = str((run_dir / "program_database").resolve())
    config["database"]["artifacts_base_path"] = str((run_dir / "artifacts").resolve())
    path = run_dir / "openevolve.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    redacted = redact(config)
    redacted["run_metadata"] = run_metadata
    (run_dir / "config.redacted.json").write_text(
        json.dumps(redacted, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "run-metadata.json").write_text(
        json.dumps(run_metadata, indent=2, sort_keys=True) + "\n",
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
