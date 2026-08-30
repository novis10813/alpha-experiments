from __future__ import annotations

import csv
import html
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from evolution.selection import CandidateResult
from evolution.spec import ResearchStatus


def write_research_report(
    candidate: CandidateResult,
    feasible: bool,
    baseline_differences: dict[str, float],
    output_directory: Path,
) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    status = ResearchStatus.ACCEPTED_ALPHA if feasible else _rejected_status(candidate)
    payload = {
        "candidate_id": candidate.candidate_id,
        "status": status,
        "discovery": asdict(candidate.discovery),
        "validation": asdict(candidate.validation) if candidate.validation else None,
        "holdout": asdict(candidate.holdout) if candidate.holdout else None,
        "baseline_differences": dict(sorted(baseline_differences.items())),
        "holdout_feedback_prohibited": True,
    }
    json_path = output_directory / "metrics.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    escaped = html.escape(json.dumps(payload, indent=2, sort_keys=True))
    html_path = output_directory / "report.html"
    html_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>Evolution report</title></head>"
        f"<body><h1>{html.escape(candidate.candidate_id)}</h1><p>Status: {status}</p><pre>{escaped}</pre></body></html>\n",
        encoding="utf-8",
    )
    return json_path, html_path


def write_alpha_signal(
    rows: Iterable[tuple[int, str, str, float]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["ts_event", "instrument_id", "alpha_name", "value"])
        writer.writerows(rows)


def _rejected_status(candidate: CandidateResult) -> str:
    validation = candidate.validation
    holdout = candidate.holdout
    if validation is None or holdout is None:
        return ResearchStatus.INCONCLUSIVE
    if validation.net_return > 0 and holdout.net_return > 0:
        return ResearchStatus.RULE_CANDIDATE
    return ResearchStatus.REJECTED

