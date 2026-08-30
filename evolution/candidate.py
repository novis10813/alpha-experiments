from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path


EVOLVE_START = "# EVOLVE-BLOCK-START"
EVOLVE_END = "# EVOLVE-BLOCK-END"
ALLOWED_IMPORT_ROOTS: set[str] = set()
FORBIDDEN_NAMES = {
    "breakpoint", "compile", "delattr", "dir", "eval", "exec", "getattr", "globals",
    "hasattr", "help", "input", "locals", "memoryview", "open", "setattr", "vars",
    "__import__", "__builtins__", "object", "type",
}
FORBIDDEN_ROOTS = {
    "asyncio", "builtins", "ctypes", "importlib", "inspect", "multiprocessing", "os",
    "pathlib", "pickle", "requests", "shutil", "socket", "subprocess", "sys", "urllib",
}
FORBIDDEN_ATTRIBUTES = {
    "__class__", "__dict__", "__bases__", "__base__", "__globals__", "__subclasses__",
    "__getattribute__", "order_factory", "submit_order", "submit_order_list", "modify_order",
}


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...]
    complexity: float


def split_evolve_block(source: str) -> tuple[str, str, str]:
    if source.count(EVOLVE_START) != 1 or source.count(EVOLVE_END) != 1:
        raise ValueError("candidate must contain exactly one evolve block")
    prefix, remainder = source.split(EVOLVE_START, 1)
    block, suffix = remainder.split(EVOLVE_END, 1)
    return prefix, block, suffix


def skeleton_hash(source: str) -> str:
    prefix, _, suffix = split_evolve_block(source)
    return hashlib.sha256((prefix + EVOLVE_START + EVOLVE_END + suffix).encode()).hexdigest()


def validate_candidate(source: str, reference_source: str) -> ValidationResult:
    errors: list[str] = []
    try:
        prefix, block, suffix = split_evolve_block(source)
        ref_prefix, _, ref_suffix = split_evolve_block(reference_source)
        if prefix != ref_prefix or suffix != ref_suffix:
            errors.append("trusted skeleton was modified")
    except ValueError as exc:
        return ValidationResult(False, (str(exc),), 0.0)

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return ValidationResult(False, (f"syntax error: {exc.msg}",), 0.0)

    evolved_tree = _parse_block(block, prefix)
    if evolved_tree is None:
        errors.append("evolve block is not valid class-body Python")
        evolved_tree = ast.Module(body=[], type_ignores=[])

    strategy_classes = [
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "EvolvedStrategy"
    ]
    if len(strategy_classes) != 1:
        errors.append("candidate must define exactly one EvolvedStrategy class")
    else:
        methods = {node.name for node in strategy_classes[0].body if isinstance(node, ast.FunctionDef)}
        for required in ("__init__", "on_start", "on_data"):
            if required not in methods:
                errors.append(f"EvolvedStrategy is missing {required}")

    for node in ast.walk(evolved_tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for name in names:
                root = name.split(".", 1)[0]
                if root not in ALLOWED_IMPORT_ROOTS:
                    errors.append(f"forbidden import: {name}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES | FORBIDDEN_ROOTS:
            errors.append(f"forbidden name: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
            errors.append(f"forbidden attribute: {node.attr}")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr != "__init__":
            errors.append(f"forbidden dunder attribute: {node.attr}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("__") and node.name != "__init__":
            errors.append(f"forbidden dunder method: {node.name}")
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name.endswith(".market") or name.endswith(".limit"):
                errors.append("candidate may only place orders through enter_long/exit_long")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            errors.append(f"forbidden statement: {type(node).__name__}")
    return ValidationResult(not errors, tuple(dict.fromkeys(errors)), float(sum(1 for _ in ast.walk(evolved_tree))))


def validate_candidate_file(program_path: str | Path, reference_path: str | Path) -> ValidationResult:
    return validate_candidate(
        Path(program_path).read_text(encoding="utf-8"),
        Path(reference_path).read_text(encoding="utf-8"),
    )


def _parse_block(block: str, prefix: str) -> ast.Module | None:
    class_indent = "    " if prefix.rstrip().endswith("class EvolvedStrategy(Strategy):") else ""
    try:
        if class_indent:
            return ast.parse("class _Candidate:\n" + block)
        return ast.parse(block)
    except SyntaxError:
        return None


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_call_name(node.value)}.{node.attr}"
    return ""
