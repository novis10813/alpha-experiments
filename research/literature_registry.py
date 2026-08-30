"""Validate and query the durable literature registry.

The registry is intentionally a small, dependency-free JSON index. It records
source-backed context and proposed repository tests; it does not store model
results or split-specific evaluation fields.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from evolution.market_state import EvolutionMarketState


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPOSITORY_ROOT / "docs" / "research" / "literature" / "registry.json"
PAPERS_ROOT = REPOSITORY_ROOT / "docs" / "research" / "literature" / "papers"

EVIDENCE_TIERS = frozenset({"primary_full_text", "primary_abstract", "metadata_only"})
STATUSES = frozenset({"verified", "provisional", "rejected", "archived"})
CLASSIFICATIONS = frozenset({"feature", "filter", "rule_idea"})
DIRECTIONS = frozenset({"positive", "negative", "mixed", "nonlinear", "uncertain"})
VALID_FEATURES = frozenset(EvolutionMarketState.FIELDS) - {"instrument_id", "ts_event", "ts_init"}

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_ARXIV_RE = re.compile(r"^(?:arxiv:)?(\d{4}\.\d{4,5})(?:v\d+)?$", re.IGNORECASE)
_FORBIDDEN_FIELD_PARTS = (
    "validation",
    "holdout",
    "forward_return",
    "forward_returns",
    "pnl",
    "drawdown",
    "fill",
    "position",
    "threshold",
    "z_score",
    "zscore",
)


class RegistryError(ValueError):
    """Raised when the literature registry fails validation."""


def _clean_identifier(value: str) -> str:
    return value.strip().strip("<>[](){}.,;\"'").lower()


def normalize_doi(value: str) -> str:
    """Return a lowercase DOI without resolver or citation decoration."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("DOI must be a nonempty string")
    normalized = _clean_identifier(value)
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    normalized = normalized.rstrip(".")
    if not _DOI_RE.fullmatch(normalized):
        raise ValueError(f"invalid DOI: {value!r}")
    return normalized


def normalize_persistent_id(value: str) -> str:
    """Normalize supported persistent IDs to the ``arxiv:<id>`` spelling."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("persistent ID must be a nonempty string")
    normalized = _clean_identifier(value)
    for prefix in (
        "https://arxiv.org/abs/",
        "http://arxiv.org/abs/",
        "https://export.arxiv.org/abs/",
        "arxiv:",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    match = _ARXIV_RE.fullmatch(normalized)
    if not match:
        raise ValueError(f"unsupported persistent ID: {value!r}")
    return f"arxiv:{match.group(1)}"


def canonical_source_id(value: str) -> str:
    """Normalize a DOI or persistent ID for registry de-duplication."""
    if not isinstance(value, str):
        raise ValueError("source ID must be a string")
    candidate = _clean_identifier(value)
    if candidate.startswith(("arxiv:", "https://arxiv.org/", "http://arxiv.org/", "https://export.arxiv.org/")):
        return normalize_persistent_id(candidate)
    doi = normalize_doi(candidate)
    if doi.startswith("10.48550/arxiv."):
        return normalize_persistent_id(doi.removeprefix("10.48550/arxiv."))
    return f"doi:{doi}"


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Load the JSON registry without performing network access."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RegistryError("registry root must be a JSON object")
    return value


def find_source(source_id: str, registry: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Find a source by DOI, DOI URL, arXiv ID, or arXiv DOI."""
    registry = load_registry() if registry is None else registry
    canonical = canonical_source_id(source_id)
    for source in registry.get("sources", []):
        if source.get("canonical_source_id") == canonical:
            return source
        for identifier in source.get("identifiers", {}).values():
            try:
                if canonical_source_id(identifier) == canonical:
                    return source
            except ValueError:
                continue
    return None


def _is_relative_paper_path(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    path = Path(value)
    return not path.is_absolute() and path.parts[:4] == ("docs", "research", "literature", "papers")


def _has_forbidden_field(value: Any, path: str = "$") -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if any(part in key_text for part in _FORBIDDEN_FIELD_PARTS):
                return f"{path}.{key} is a derived/result field and is not allowed"
            found = _has_forbidden_field(item, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = _has_forbidden_field(item, f"{path}[{index}]")
            if found:
                return found
    return None


def validate_registry(registry: dict[str, Any], repo_root: Path = REPOSITORY_ROOT) -> list[str]:
    """Return all registry validation errors, including filesystem checks."""
    errors: list[str] = []
    if not isinstance(registry, dict):
        return ["registry root must be a JSON object"]
    if registry.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    sources = registry.get("sources")
    if not isinstance(sources, list):
        return [*errors, "sources must be a list"]
    forbidden = _has_forbidden_field(registry)
    if forbidden:
        errors.append(forbidden)

    source_ids: set[str] = set()
    paper_ids: set[str] = set()
    identifier_ids: dict[str, str] = {}
    hypothesis_ids: set[str] = set()
    required_source_fields = {
        "paper_id", "canonical_source_id", "title", "authors", "year", "source_url",
        "note_path", "evidence_tier", "tags", "identifiers", "hypotheses", "status",
    }
    required_hypothesis_fields = {
        "hypothesis_id", "statement", "mechanism", "primary_features", "context_features",
        "expected_direction", "diagnostic_horizons", "classification", "prerequisites", "missing_fields",
    }

    for index, source in enumerate(sources):
        prefix = f"sources[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{prefix} must be an object")
            continue
        missing = required_source_fields - source.keys()
        errors.extend(f"{prefix} missing {field}" for field in sorted(missing))
        source_id = source.get("canonical_source_id")
        if not isinstance(source_id, str):
            errors.append(f"{prefix}.canonical_source_id must be a string")
        else:
            try:
                if canonical_source_id(source_id) != source_id:
                    errors.append(f"{prefix}.canonical_source_id is not normalized")
            except ValueError as exc:
                errors.append(f"{prefix}.canonical_source_id: {exc}")
            if source_id in source_ids:
                errors.append(f"duplicate canonical source ID: {source_id}")
            source_ids.add(source_id)

        paper_id = source.get("paper_id")
        if not isinstance(paper_id, str) or not paper_id.strip():
            errors.append(f"{prefix}.paper_id must be nonempty")
        elif paper_id in paper_ids:
            errors.append(f"duplicate paper ID: {paper_id}")
        else:
            paper_ids.add(paper_id)

        if not isinstance(source.get("title"), str) or not source.get("title", "").strip():
            errors.append(f"{prefix}.title must be nonempty")
        authors = source.get("authors")
        if not isinstance(authors, list) or not authors or not all(isinstance(item, str) and item.strip() for item in authors):
            errors.append(f"{prefix}.authors must be a nonempty list of strings")
        if not isinstance(source.get("year"), int) or source.get("year", 0) <= 0:
            errors.append(f"{prefix}.year must be a positive integer")
        source_url = source.get("source_url")
        if not isinstance(source_url, str) or urlsplit(source_url).scheme not in {"http", "https"}:
            errors.append(f"{prefix}.source_url must be an http(s) URL")
        note_path = source.get("note_path")
        if not _is_relative_paper_path(note_path):
            errors.append(f"{prefix}.note_path must be under docs/research/literature/papers")
        elif not (repo_root / note_path).is_file():
            errors.append(f"missing note: {note_path}")
        if source.get("evidence_tier") not in EVIDENCE_TIERS:
            errors.append(f"{prefix}.evidence_tier is not allowed")
        tags = source.get("tags")
        if not isinstance(tags, list) or not tags or not all(isinstance(item, str) and item.strip() for item in tags):
            errors.append(f"{prefix}.tags must be a nonempty list of strings")
        if source.get("status") not in STATUSES:
            errors.append(f"{prefix}.status is not allowed")

        identifiers = source.get("identifiers")
        if not isinstance(identifiers, dict) or not identifiers:
            errors.append(f"{prefix}.identifiers must be a nonempty object")
        else:
            for name, raw_value in identifiers.items():
                try:
                    normalized = normalize_doi(raw_value) if name == "doi" else normalize_persistent_id(raw_value) if name == "persistent_id" else None
                    if normalized is None:
                        errors.append(f"{prefix}.identifiers.{name} is not a supported identifier")
                        continue
                    identifier_canonical = canonical_source_id(normalized)
                    owner = identifier_ids.get(identifier_canonical)
                    if owner and owner != paper_id:
                        errors.append(f"duplicate DOI or persistent ID: {identifier_canonical}")
                    identifier_ids[identifier_canonical] = paper_id
                    if identifier_canonical != source_id:
                        errors.append(f"{prefix}.canonical_source_id does not match identifiers")
                except ValueError as exc:
                    errors.append(f"{prefix}.identifiers.{name}: {exc}")

        hypotheses = source.get("hypotheses")
        if not isinstance(hypotheses, list) or not hypotheses:
            errors.append(f"{prefix}.hypotheses must be a nonempty list")
            continue
        for hindex, hypothesis in enumerate(hypotheses):
            hprefix = f"{prefix}.hypotheses[{hindex}]"
            if not isinstance(hypothesis, dict):
                errors.append(f"{hprefix} must be an object")
                continue
            errors.extend(f"{hprefix} missing {field}" for field in sorted(required_hypothesis_fields - hypothesis.keys()))
            hypothesis_id = hypothesis.get("hypothesis_id")
            if not isinstance(hypothesis_id, str) or not hypothesis_id.strip():
                errors.append(f"{hprefix}.hypothesis_id must be nonempty")
            elif hypothesis_id in hypothesis_ids:
                errors.append(f"duplicate hypothesis ID: {hypothesis_id}")
            else:
                hypothesis_ids.add(hypothesis_id)
            for field in ("statement", "mechanism"):
                if not isinstance(hypothesis.get(field), str) or not hypothesis.get(field, "").strip():
                    errors.append(f"{hprefix}.{field} must be nonempty")
            for field in ("primary_features", "context_features", "prerequisites", "missing_fields"):
                values = hypothesis.get(field)
                if not isinstance(values, list) or not all(isinstance(item, str) and item.strip() for item in values):
                    errors.append(f"{hprefix}.{field} must be a list of strings")
            for field in ("primary_features", "context_features"):
                values = hypothesis.get(field, [])
                if isinstance(values, list):
                    for feature in values:
                        if feature not in VALID_FEATURES:
                            errors.append(f"{hprefix}.{field} has invalid EvolutionMarketState feature: {feature}")
            if hypothesis.get("expected_direction") not in DIRECTIONS:
                errors.append(f"{hprefix}.expected_direction is not allowed")
            horizons = hypothesis.get("diagnostic_horizons")
            if (
                not isinstance(horizons, list)
                or not horizons
                or any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in horizons)
                or len(set(horizons)) != len(horizons)
            ):
                errors.append(f"{hprefix}.diagnostic_horizons must be positive unique integers")
            if hypothesis.get("classification") not in CLASSIFICATIONS:
                errors.append(f"{hprefix}.classification is not allowed")
    return errors


def assert_valid_registry(registry: dict[str, Any] | None = None, repo_root: Path = REPOSITORY_ROOT) -> None:
    errors = validate_registry(load_registry() if registry is None else registry, repo_root)
    if errors:
        raise RegistryError("\n".join(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and query the literature registry")
    parser.add_argument("--validate", action="store_true", help="validate registry JSON and referenced notes")
    parser.add_argument("--check-source", metavar="DOI_OR_ID", help="report whether a source is already registered")
    args = parser.parse_args(argv)
    if not args.validate and not args.check_source:
        parser.error("choose --validate or --check-source")
    try:
        registry = load_registry()
        if args.validate:
            assert_valid_registry(registry)
            print(f"valid: {REGISTRY_PATH}")
        if args.check_source:
            source = find_source(args.check_source, registry)
            if source is None:
                print(f"not found: {canonical_source_id(args.check_source)}")
            else:
                print(f"exists: {source['canonical_source_id']} ({source['paper_id']})")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
