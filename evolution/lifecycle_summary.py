"""Discovery-only diagnostics for OpenEvolve lifecycle runs."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from evolution.metrics import REJECTED_SCORE
from evolution.signatures import source_signature


CATEGORIES = (
    "accepted_candidate",
    "diff_parse_failure",
    "provider_timeout",
    "provider_http_error",
    "evaluator_candidate_rejection",
    "unclassified_failure",
)
_ITERATION_ERROR = re.compile(r"Iteration (\d+) error: (.*)")
_ITERATION_COMPLETED = re.compile(
    r"Iteration (\d+): Program ([^ ]+) \(parent: ([^)]*)\) completed"
)
_HTTP_STATUS = re.compile(r'HTTP/\d(?:\.\d)?\s+(\d{3})\b')


def summarize_lifecycle(run_directory: Path) -> dict[str, Any]:
    """Write and return a best-effort summary from run logs and local artifacts.

    This function only reads discovery-run logs, database/checkpoint program
    payloads, and top-candidate source files. It does not evaluate candidates or
    inspect validation/holdout artifacts.
    """
    programs = _load_programs(run_directory)
    _load_program_artifacts(run_directory, programs)
    logs = _load_logs(run_directory)
    events = _classify_events(logs, programs)
    sources = _source_uniqueness(run_directory)
    counts = Counter(event["category"] for event in events)
    summary = {
        "schema_version": 1,
        "discovery_only": True,
        "attempted_iterations": len(events),
        "category_counts": {category: counts.get(category, 0) for category in CATEGORIES},
        "events": events,
        "semantic_source_uniqueness": sources,
    }
    target = run_directory / "lifecycle-summary.json"
    target.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _load_logs(run_directory: Path) -> list[str]:
    paths = sorted((run_directory / "logs").glob("*.log"))
    runner_log = run_directory / "runner.log"
    if runner_log.is_file():
        paths.append(runner_log)
    return [path.read_text(encoding="utf-8", errors="replace") for path in paths]


def _load_programs(run_directory: Path) -> dict[str, dict[str, Any]]:
    programs: dict[str, dict[str, Any]] = {}
    roots = [run_directory / "program_database" / "programs"]
    checkpoints = run_directory / "checkpoints"
    if checkpoints.is_dir():
        roots.extend(sorted(checkpoints.glob("checkpoint_*/programs")))
    for root in roots:
        for path in root.glob("*.json") if root.is_dir() else ():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and payload.get("id"):
                programs[str(payload["id"])] = payload
    return programs


def _load_program_artifacts(run_directory: Path, programs: dict[str, dict[str, Any]]) -> None:
    for program in programs.values():
        artifact_dir = program.get("artifact_dir")
        if not isinstance(artifact_dir, str):
            continue
        path = Path(artifact_dir)
        if not path.is_absolute():
            path = run_directory / path
        evaluation = path / "evaluation.json"
        if evaluation.is_file():
            try:
                program["_evaluation_artifact"] = json.loads(evaluation.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue


def _classify_events(logs: list[str], programs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    events: dict[int, dict[str, Any]] = {}
    recent_provider_signal: str | None = None
    for text in logs:
        for line in text.splitlines():
            status_match = _HTTP_STATUS.search(line)
            if status_match and int(status_match.group(1)) >= 400:
                recent_provider_signal = "provider_http_error"
            elif "failed with timeout" in line.lower() or "timeout on attempt" in line.lower():
                recent_provider_signal = "provider_timeout"

            completed = _ITERATION_COMPLETED.search(line)
            if completed:
                iteration = int(completed.group(1))
                program_id = completed.group(2)
                payload = programs.get(program_id, {})
                category = (
                    "evaluator_candidate_rejection"
                    if _is_rejected_program(payload)
                    else "accepted_candidate"
                )
                events[iteration] = {
                    "iteration": iteration,
                    "category": category,
                    "program_id": program_id,
                }
                continue

            failed = _ITERATION_ERROR.search(line)
            if failed:
                iteration = int(failed.group(1))
                message = failed.group(2)
                category = _failure_category(message, recent_provider_signal)
                events[iteration] = {
                    "iteration": iteration,
                    "category": category,
                    "reason": message[:500],
                }
                recent_provider_signal = None
    return [events[key] for key in sorted(events)]


def _failure_category(message: str, recent_provider_signal: str | None) -> str:
    lowered = message.lower()
    if "no valid diff" in lowered or "diff" in lowered and "parse" in lowered:
        return "diff_parse_failure"
    if "timeout" in lowered or not message.strip() and recent_provider_signal == "provider_timeout":
        return "provider_timeout"
    if re.search(r"\b(?:http|error code|status)\D{0,8}[45]\d{2}\b", lowered):
        return "provider_http_error"
    if recent_provider_signal in {"provider_timeout", "provider_http_error"}:
        return recent_provider_signal
    if any(token in lowered for token in ("candidate", "syntax", "lifecycle", "sandbox", "order rejection")):
        return "evaluator_candidate_rejection"
    return "unclassified_failure"


def _is_rejected_program(payload: dict[str, Any]) -> bool:
    metrics = payload.get("metrics", {})
    try:
        if float(metrics.get("combined_score", 0.0)) <= REJECTED_SCORE:
            return True
    except (TypeError, ValueError):
        pass
    artifacts = payload.get("artifacts_json")
    decoded = {}
    if isinstance(artifacts, str):
        try:
            decoded = json.loads(artifacts)
        except json.JSONDecodeError:
            decoded = {}
    if not decoded:
        decoded = payload.get("_evaluation_artifact", {})
    return isinstance(decoded, dict) and decoded.get("stage") in {1, 2}


def _source_uniqueness(run_directory: Path) -> dict[str, Any]:
    sources: dict[str, str] = {}
    top = run_directory / "top_candidates"
    index = top / "index.json"
    if index.is_file():
        try:
            rows = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            rows = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            candidate_id = str(row.get("candidate_id", row.get("rank", len(sources))))
            path = Path(str(row.get("program_path", "")))
            if not path.is_file():
                path = top / path.name
            if path.is_file():
                try:
                    sources[candidate_id] = path.read_text(encoding="utf-8")
                except OSError:
                    pass

    checkpoints = run_directory / "checkpoints"
    checkpoint_dirs = sorted(checkpoints.glob("checkpoint_*") if checkpoints.is_dir() else ())
    if checkpoint_dirs:
        for path in (checkpoint_dirs[-1] / "programs").glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            code = payload.get("code") if isinstance(payload, dict) else None
            if isinstance(code, str):
                candidate_id = str(payload.get("id", path.stem))
                # Prefer the checkpoint source because it is the complete lineage artifact.
                sources[candidate_id] = code

    signatures: dict[str, list[str]] = {}
    invalid = []
    for candidate_id, source in sources.items():
        try:
            signature = source_signature(source)
        except (SyntaxError, ValueError):
            invalid.append(candidate_id)
            continue
        signatures.setdefault(signature, []).append(candidate_id)
    duplicate_groups = [sorted(ids) for ids in signatures.values() if len(ids) > 1]
    return {
        "program_count": len(sources),
        "valid_signature_count": len(signatures),
        "invalid_signature_count": len(invalid),
        "invalid_candidates": sorted(invalid),
        "duplicate_groups": duplicate_groups,
    }
