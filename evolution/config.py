from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evolution.families import EvolutionFamily

import yaml

from evolution.spec import run_directory


BASE_CONFIG = Path(__file__).parent / "configs" / "base.yaml"
SECRET_NAMES = {"api_key", "access_key", "secret_key", "password", "token"}
_FAMILY_RULE_GRAMMAR = """
Family rule grammar (schema-v2): RULE_SPEC is exactly one class-level literal
plain mapping with keys family_id, entry, exit, and cooldown_bars. entry and
exit each have a flat conditions list of {feature, op, value}; entry also has
confirmations, while exit has confirmations, min_hold_bars, and mode (all or
any). Use only trusted features and gt/gte/lt/lte. Each mutation changes one
oralizable rule component only: one feature, operator, threshold, confirmation
count, exit mode, minimum hold, or cooldown. Do not add code or unrestricted
LLM feedback.
"""
_FAMILY_DIFF_PROMPT = """# Declarative family mutation task

Edit only the class-level `RULE_SPEC` literal inside the EVOLVE block. Keep the
exact schema-v2 flat mapping grammar from the family context. Conditions must be
literal mappings with exactly `feature`, `op`, and `value`; do not add nested
logic, methods, imports, or executable expressions. Make one oralizable rule
component mutation per proposal and preserve the family_id. Return only a
SEARCH/REPLACE diff whose replacement remains a RULE_SPEC literal. Do not use
unrestricted LLM feedback.
"""


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
    existing_metadata_path = run_dir / "run_metadata.json"
    if not existing_metadata_path.exists():
        existing_metadata_path = run_dir / "run-metadata.json"
    if existing_metadata_path.exists():
        existing_metadata = json.loads(existing_metadata_path.read_text(encoding="utf-8"))
        for key in ("instrument_id", "run_id"):
            if key in existing_metadata and existing_metadata[key] != run_metadata[key]:
                raise ValueError(f"run metadata {key} does not match")
        for key in ("family_id", "hypothesis", "seed_program_sha256", "composed_prompt_sha256"):
            if key in existing_metadata:
                run_metadata[key] = existing_metadata[key]
    if advancement_record is not None:
        run_metadata["advancement_record"] = str(advancement_record.resolve())
    template_dir = Path(config["prompt"]["template_dir"])
    if not template_dir.is_absolute():
        template_dir = (Path(__file__).parents[1] / template_dir).resolve()
    if family is not None:
        template_dir = run_dir / "prompts"
        template_dir.mkdir(parents=True, exist_ok=True)
        common_system = (Path(__file__).parent / "prompts" / "system_message.txt").read_text(encoding="utf-8")
        common_diff = (Path(__file__).parent / "prompts" / "diff_user.txt").read_text(encoding="utf-8")
        (template_dir / "system_message.txt").write_text(
            common_system + "\n\n# Family context\n" + _FAMILY_RULE_GRAMMAR + "\n" + family.prompt_context + "\n",
            encoding="utf-8",
        )
        (template_dir / "diff_user.txt").write_text(
            _FAMILY_DIFF_PROMPT + "\n# Family identifier\n" + family.family_id + "\n\n" + common_diff,
            encoding="utf-8",
        )
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
    encoded_metadata = json.dumps(run_metadata, indent=2, sort_keys=True) + "\n"
    (run_dir / "run_metadata.json").write_text(encoded_metadata, encoding="utf-8")
    (run_dir / "run-metadata.json").write_text(encoded_metadata, encoding="utf-8")
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
