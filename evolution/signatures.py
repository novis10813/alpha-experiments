from __future__ import annotations

import ast
import hashlib
import json

from evolution.candidate import split_evolve_block
from evolution.rules import rule_source_signature


def source_signature(source: str) -> str:
    """Sign declarative rules canonically and legacy evolve blocks by AST."""
    if _is_declarative_source(source):
        return rule_source_signature(source)
    try:
        _, block, _ = split_evolve_block(source)
        tree = ast.parse("class _Candidate:\n" + block)
    except (SyntaxError, ValueError):
        tree = ast.parse(source)
    normalized = ast.dump(tree, annotate_fields=True, include_attributes=False)
    return _sha256(normalized)


def _is_declarative_source(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    return any(
        isinstance(node, ast.ClassDef)
        and node.name == "EvolvedStrategy"
        and any(isinstance(base, ast.Name) and base.id == "RuleInterpreterStrategy" for base in node.bases)
        for node in tree.body
    )


def behavior_signature(fold_signatures: list[str] | tuple[str, ...]) -> str:
    """Hash ordered per-fold behavior signatures into one candidate signature."""
    return _sha256(json.dumps(list(fold_signatures), separators=(",", ":")))


def behavior_signature_from_reports(*reports):
    """Hash deterministic position/trade report rows without rerunning a candidate."""
    payload = []
    for label, report in zip(("positions", "fills", "orders"), reports, strict=True):
        payload.append({"label": label, "rows": _report_rows(report)})
    return _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))


def behavior_signature_from_payload(payload):
    folds = payload.get("folds", [])
    fold_signatures = [
        str(fold["behavior_signature"])
        for fold in folds
        if fold.get("behavior_signature") is not None
    ]
    if len(fold_signatures) == len(folds):
        return behavior_signature(fold_signatures)
    return behavior_signature([
        _sha256(json.dumps({
            "positions": fold.get("positions", []),
            "trades": fold.get("trades", fold.get("fills", [])),
            "orders": fold.get("orders", []),
        }, sort_keys=True, separators=(",", ":"), default=str))
        for fold in folds
    ])


def _report_rows(report):
    if report is None or len(report) == 0:
        return []
    columns = sorted(column for column in report.columns if not _excluded_behavior_column(str(column)))
    return [[str(value) for value in row] for row in report[columns].itertuples(index=False, name=None)]


def _excluded_behavior_column(column: str) -> bool:
    name = column.lower()
    return (
        name == "id"
        or name.endswith("_id")
        or name in {"commissions", "commission", "realized_pnl", "realized_return"}
        or "fee" in name
        or "pnl" in name
        or "return" in name
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
