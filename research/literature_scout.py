"""Automated literature scout for hypothesis discovery.

Searches academic papers via Semantic Scholar, evaluates relevance against
the repository's ``EvolutionMarketState`` feature set using an LLM, and
outputs structured hypothesis candidates to a staging file for human review.

Usage::

    uv run python -m research.literature_scout search
    uv run python -m research.literature_scout status
    uv run python -m research.literature_scout approve <paper_id>

Requires ``OPENROUTER_API_KEY`` in the environment (same as evolution).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evolution.market_state import EvolutionMarketState
from research.academic_search import PaperResult, search_multiple
from research.literature_registry import (
    REGISTRY_PATH,
    REPOSITORY_ROOT,
    canonical_source_id,
    find_source,
    load_registry,
    validate_registry,
)
from research.llm_client import chat_completion


STAGING_PATH = REGISTRY_PATH.parent / "staging.json"
PAPERS_ROOT = REGISTRY_PATH.parent / "papers"
NOTE_TEMPLATE = REPOSITORY_ROOT / "docs" / "research" / "templates" / "literature-note-template.md"

# Features available for hypothesis mapping (exclude identifiers/timestamps)
_VALID_FEATURES = sorted(
    set(EvolutionMarketState.FIELDS) - {"instrument_id", "ts_event", "ts_init"}
)

# Feature descriptions for LLM context
_FEATURE_DESCRIPTIONS: dict[str, str] = {
    "open": "1-minute bar open price",
    "high": "1-minute bar high price",
    "low": "1-minute bar low price",
    "close": "1-minute bar close price",
    "volume": "total traded volume in the 1-minute bar",
    "trade_count": "number of trades in the bar",
    "buy_trade_count": "number of buyer-initiated trades",
    "sell_trade_count": "number of seller-initiated trades",
    "buy_volume": "buyer-initiated volume",
    "sell_volume": "seller-initiated volume",
    "trade_imbalance": "normalized trade count imbalance: (buy-sell)/(buy+sell)",
    "volume_imbalance": "normalized volume imbalance: (buy_vol-sell_vol)/(buy_vol+sell_vol)",
    "depth10_obi_mean": "mean order book imbalance across the bar (top 10 levels)",
    "depth10_obi_last": "last snapshot order book imbalance (top 10 levels)",
    "depth10_obi_min": "minimum order book imbalance snapshot in the bar",
    "depth10_obi_max": "maximum order book imbalance snapshot in the bar",
    "best_bid": "best bid price at bar end",
    "best_ask": "best ask price at bar end",
    "spread_bps": "bid-ask spread in basis points at bar end",
    "return_5m": "cumulative return over the last 5 minutes",
    "return_15m": "cumulative return over the last 15 minutes",
    "return_60m": "cumulative return over the last 60 minutes",
    "close_location": "where the close sits within the high-low range [0,1]",
    "realized_volatility_15m": "realized volatility over 15-minute window",
    "relative_volume_15m": "current volume relative to 15-minute rolling mean",
    "relative_trade_density_15m": "current trade density relative to 15-minute rolling mean",
    "signed_flow_persistence_5m": "persistence of signed trade flow direction over 5 minutes",
    "obi_change_5m": "change in order book imbalance over 5 minutes",
    "relative_spread_15m": "current spread relative to 15-minute rolling mean",
}


# ── Query generation ────────────────────────────────────────────────


def _build_query_prompt(
    existing_titles: list[str],
    existing_hypothesis_ids: list[str],
) -> list[dict[str, str]]:
    feature_block = "\n".join(
        f"  - {name}: {_FEATURE_DESCRIPTIONS.get(name, 'no description')}"
        for name in _VALID_FEATURES
    )
    existing_block = "\n".join(f"  - {t}" for t in existing_titles) or "  (none)"
    hypothesis_block = "\n".join(f"  - {h}" for h in existing_hypothesis_ids) or "  (none)"

    return [
        {
            "role": "system",
            "content": textwrap.dedent("""\
                You are an academic research assistant helping find relevant
                quantitative finance and market microstructure papers. Your goal
                is to generate diverse search queries that will find papers whose
                findings can be mapped to the available feature set of a
                cryptocurrency trading research system.
            """),
        },
        {
            "role": "user",
            "content": textwrap.dedent(f"""\
                Generate 12 academic search queries to find papers relevant to
                our trading research system. The system trades BTC, ETH, and BNB
                perpetual futures on Binance using 1-minute bars with these features:

                {feature_block}

                Papers already in the registry (avoid duplicating these topics):
                {existing_block}

                Existing hypothesis IDs (avoid redundancy):
                {hypothesis_block}

                Requirements for the queries:
                1. Cover diverse research areas: order book microstructure, trade flow,
                   volatility regimes, momentum/mean-reversion at intraday frequency,
                   spread dynamics, liquidity, cryptocurrency-specific patterns, etc.
                2. Use academic terminology that Semantic Scholar will match well.
                3. Each query should be 3-8 words.
                4. Avoid generic queries like "trading strategy" or "machine learning finance".
                5. Focus on papers that study observable market features and short-horizon
                   price behavior, not portfolio optimization or macro factors.

                Return ONLY a JSON array of query strings, no explanation.
                Example: ["order flow imbalance price impact", "bid ask spread regime switching"]
            """),
        },
    ]


def generate_queries(registry: dict[str, Any]) -> list[str]:
    """Use LLM to generate diverse search queries."""
    sources = registry.get("sources", [])
    titles = [s["title"] for s in sources if s.get("title")]
    hypothesis_ids = []
    for s in sources:
        for h in s.get("hypotheses", []):
            if h.get("hypothesis_id"):
                hypothesis_ids.append(h["hypothesis_id"])

    print("[scout] generating search queries …")
    messages = _build_query_prompt(titles, hypothesis_ids)
    response = chat_completion(messages, temperature=0.7)

    # Parse JSON array from response (handle markdown fences)
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```\w*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    try:
        queries = json.loads(cleaned)
        if not isinstance(queries, list):
            raise ValueError("expected a JSON array")
        queries = [q.strip() for q in queries if isinstance(q, str) and q.strip()]
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"  [scout] failed to parse queries: {exc}")
        print(f"  [scout] raw response: {response[:500]}")
        # Fallback queries
        queries = [
            "order book imbalance cryptocurrency price prediction",
            "trade flow toxicity limit order book",
            "bid ask spread regime crypto futures",
            "intraday volatility clustering cryptocurrency",
            "momentum reversal high frequency crypto",
            "market microstructure cryptocurrency perpetual",
            "order flow signed volume price impact",
            "liquidity provision adverse selection crypto",
        ]
        print(f"  [scout] using {len(queries)} fallback queries")

    print(f"  [scout] generated {len(queries)} queries")
    return queries


# ── Deduplication ────────────────────────────────────────────────────


def _known_source_ids(registry: dict[str, Any]) -> set[str]:
    """Collect all canonical source IDs from the registry."""
    ids: set[str] = set()
    for source in registry.get("sources", []):
        csid = source.get("canonical_source_id")
        if csid:
            ids.add(csid)
        for identifier in source.get("identifiers", {}).values():
            try:
                ids.add(canonical_source_id(identifier))
            except ValueError:
                pass
    return ids


def _staging_source_ids() -> set[str]:
    """Collect canonical source IDs already in staging."""
    if not STAGING_PATH.exists():
        return set()
    try:
        staging = json.loads(STAGING_PATH.read_text(encoding="utf-8"))
        return _known_source_ids(staging)
    except (json.JSONDecodeError, OSError):
        return set()


def dedup_papers(
    papers: list[PaperResult],
    registry: dict[str, Any],
) -> list[PaperResult]:
    """Remove papers already in registry or staging."""
    known = _known_source_ids(registry) | _staging_source_ids()
    novel: list[PaperResult] = []
    for paper in papers:
        paper_ids = paper.canonical_ids()
        if not paper_ids:
            # Paper has no DOI or arXiv ID — skip
            continue
        if any(pid in known for pid in paper_ids):
            continue
        novel.append(paper)
    return novel


# ── Relevance filtering ─────────────────────────────────────────────


def _build_relevance_prompt(papers: list[PaperResult]) -> list[dict[str, str]]:
    feature_summary = ", ".join(_VALID_FEATURES)
    papers_block = ""
    for i, p in enumerate(papers):
        abstract_trunc = p.abstract[:600] + ("…" if len(p.abstract) > 600 else "")
        papers_block += f"\n[{i}] {p.title} ({p.year})\n{abstract_trunc}\n"

    return [
        {
            "role": "system",
            "content": textwrap.dedent("""\
                You evaluate academic papers for relevance to a cryptocurrency
                trading research system. The system uses 1-minute bars on
                BTCUSDT, ETHUSDT, BNBUSDT Binance perpetual futures with a
                long/flat constraint.
            """),
        },
        {
            "role": "user",
            "content": textwrap.dedent(f"""\
                Rate each paper's relevance to our research system on a 0-10 scale.

                Our available features (1-minute bar frequency):
                {feature_summary}

                Papers to evaluate:
                {papers_block}

                Scoring criteria:
                - 8-10: Directly studies features we have (order book depth, trade
                  flow, spread, short-horizon returns) in crypto or similar markets
                - 6-7: Studies related microstructure phenomena that could map to
                  our features with reasonable interpretation
                - 3-5: Studies relevant market concepts but at different frequency,
                  asset class, or abstraction level
                - 0-2: Unrelated or purely theoretical without observable feature mapping

                Return ONLY a JSON array of objects, one per paper, in order:
                [{{"index": 0, "score": 8, "reason": "brief reason"}}, ...]
            """),
        },
    ]


def filter_relevant(papers: list[PaperResult], threshold: int = 6) -> list[PaperResult]:
    """Use LLM to score papers and keep only those above threshold."""
    if not papers:
        return []

    # Process in batches of 10 to stay within token limits
    relevant: list[PaperResult] = []
    batch_size = 10

    for start in range(0, len(papers), batch_size):
        batch = papers[start : start + batch_size]
        print(f"[scout] evaluating relevance for {len(batch)} papers …")
        messages = _build_relevance_prompt(batch)
        response = chat_completion(messages, temperature=0.2)

        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```\w*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)

        try:
            scores = json.loads(cleaned)
            if not isinstance(scores, list):
                raise ValueError("expected array")
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"  [scout] failed to parse relevance scores: {exc}")
            # Keep all papers on parse failure
            relevant.extend(batch)
            continue

        for item in scores:
            idx = item.get("index", -1)
            score = item.get("score", 0)
            reason = item.get("reason", "")
            if 0 <= idx < len(batch):
                if score >= threshold:
                    print(f"  [scout] ✓ [{score}/10] {batch[idx].title[:60]} — {reason}")
                    relevant.append(batch[idx])
                else:
                    print(f"  [scout] ✗ [{score}/10] {batch[idx].title[:60]}")

    return relevant


# ── Hypothesis extraction ────────────────────────────────────────────


def _build_extraction_prompt(paper: PaperResult) -> list[dict[str, str]]:
    feature_block = "\n".join(
        f"  - {name}: {_FEATURE_DESCRIPTIONS.get(name, '')}"
        for name in _VALID_FEATURES
    )

    return [
        {
            "role": "system",
            "content": textwrap.dedent("""\
                You extract structured, testable hypotheses from academic papers
                for a cryptocurrency trading research system. Each hypothesis must
                map to observable features available at the end of a completed
                1-minute bar. No lookahead, no result-derived fields.
            """),
        },
        {
            "role": "user",
            "content": textwrap.dedent(f"""\
                Extract testable hypotheses from this paper for our research system.

                Paper: {paper.title} ({paper.year})
                Authors: {', '.join(paper.authors[:5])}
                Abstract: {paper.abstract}

                Available EvolutionMarketState features:
                {feature_block}

                Generate a JSON object for a registry source entry. Follow this
                schema exactly:

                {{
                  "paper_id": "<author-year slug, e.g. cont-kukanov-stoikov-2014>",
                  "title": "<exact paper title>",
                  "authors": ["<author1>", ...],
                  "year": <int>,
                  "source_url": "<DOI URL or arXiv URL>",
                  "note_path": "docs/research/literature/papers/<paper_id>.md",
                  "evidence_tier": "primary_abstract",
                  "tags": ["<tag1>", "<tag2>", ...],
                  "status": "provisional",
                  "hypotheses": [
                    {{
                      "hypothesis_id": "<paper_id>-<short-label>-001",
                      "statement": "<one-sentence testable hypothesis using only
                        features from the list above>",
                      "mechanism": "<brief market-structure mechanism explanation>",
                      "primary_features": ["<feature_name>", ...],
                      "context_features": ["<feature_name>", ...],
                      "expected_direction": "positive|negative|mixed|nonlinear|uncertain",
                      "diagnostic_horizons": [1, 5, 15],
                      "classification": "feature|filter|rule_idea",
                      "prerequisites": ["<what must be verified first>"],
                      "missing_fields": ["<what the repository lacks>"]
                    }}
                  ]
                }}

                Rules:
                1. primary_features and context_features MUST use only names from
                   the feature list above. No invented features.
                2. Generate 1-3 hypotheses per paper, each testable with available features.
                3. classification should be "feature" if the paper studies a predictive
                   variable, "filter" if it studies a conditioning/modulating variable,
                   "rule_idea" if it suggests an entry/exit signal.
                4. Do not include validation, holdout, forward_return, pnl, drawdown,
                   threshold, or any result-derived fields.
                5. Use the paper's DOI URL if available, otherwise arXiv URL.
                6. Paper ID should be lowercase, hyphenated: "<first-author-lastname>-<year>".

                DOI: {paper.doi or 'not available'}
                arXiv ID: {paper.arxiv_id or 'not available'}

                Return ONLY the JSON object, no explanation.
            """),
        },
    ]


def extract_hypotheses(paper: PaperResult) -> dict[str, Any] | None:
    """Use LLM to extract structured hypotheses from a paper."""
    print(f"[scout] extracting hypotheses from: {paper.title[:70]} …")
    messages = _build_extraction_prompt(paper)
    response = chat_completion(messages, temperature=0.3, max_tokens=3000)

    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```\w*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)

    try:
        entry = json.loads(cleaned)
        if not isinstance(entry, dict):
            raise ValueError("expected JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"  [scout] failed to parse extraction: {exc}")
        return None

    # Add canonical_source_id and identifiers
    identifiers: dict[str, str] = {}
    source_url = entry.get("source_url", "")
    if paper.doi:
        identifiers["doi"] = paper.doi.lower()
        entry["canonical_source_id"] = f"doi:{paper.doi.lower()}"
        if not source_url:
            entry["source_url"] = f"https://doi.org/{paper.doi}"
    elif paper.arxiv_id:
        identifiers["persistent_id"] = f"arxiv:{paper.arxiv_id}"
        entry["canonical_source_id"] = f"arxiv:{paper.arxiv_id}"
        if not source_url:
            entry["source_url"] = f"https://arxiv.org/abs/{paper.arxiv_id}"

    if not identifiers:
        print(f"  [scout] skipping — no DOI or arXiv ID")
        return None

    entry["identifiers"] = identifiers
    entry["evidence_tier"] = "primary_abstract"
    entry["status"] = "provisional"

    # Validate features
    valid = set(_VALID_FEATURES)
    for hyp in entry.get("hypotheses", []):
        for field_key in ("primary_features", "context_features"):
            features = hyp.get(field_key, [])
            if isinstance(features, list):
                hyp[field_key] = [f for f in features if f in valid]

    n_hyp = len(entry.get("hypotheses", []))
    print(f"  [scout] extracted {n_hyp} hypothesis(es)")
    return entry


# ── Staging I/O ──────────────────────────────────────────────────────


def load_staging() -> dict[str, Any]:
    """Load staging.json or return empty structure."""
    if STAGING_PATH.exists():
        try:
            return json.loads(STAGING_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "schema_version": 1,
        "description": "Staging area for literature scout. Review and approve entries before they enter the main registry.",
        "sources": [],
    }


def save_staging(staging: dict[str, Any]) -> None:
    """Write staging.json with deterministic formatting."""
    STAGING_PATH.write_text(
        json.dumps(staging, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def add_to_staging(entry: dict[str, Any]) -> bool:
    """Add a source entry to staging.json, deduplicating by canonical_source_id."""
    staging = load_staging()
    existing_ids = {s.get("canonical_source_id") for s in staging.get("sources", [])}
    csid = entry.get("canonical_source_id")
    if csid in existing_ids:
        print(f"  [scout] already in staging: {csid}")
        return False
    staging["sources"].append(entry)
    save_staging(staging)
    return True


# ── CLI commands ─────────────────────────────────────────────────────


def cmd_search(args: argparse.Namespace) -> int:
    """Run the full search → filter → extract → stage pipeline."""
    registry = load_registry()

    # 1. Generate queries
    queries = generate_queries(registry)

    # 2. Search papers
    print(f"\n[scout] searching Semantic Scholar ({len(queries)} queries) …")
    papers = search_multiple(
        queries,
        limit_per_query=args.limit,
        year_range=args.year_range,
    )
    print(f"[scout] found {len(papers)} unique papers with abstracts")

    # 3. Dedup against registry and staging
    novel = dedup_papers(papers, registry)
    print(f"[scout] {len(novel)} papers after deduplication")
    if not novel:
        print("[scout] no new papers found")
        return 0

    # 4. Filter by relevance
    relevant = filter_relevant(novel, threshold=args.threshold)
    print(f"\n[scout] {len(relevant)} papers passed relevance filter")
    if not relevant:
        print("[scout] no relevant papers found")
        return 0

    # 5. Extract hypotheses and stage
    staged = 0
    for paper in relevant:
        entry = extract_hypotheses(paper)
        if entry and add_to_staging(entry):
            staged += 1

    print(f"\n[scout] staged {staged} new entries → {STAGING_PATH}")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    """Show staging summary."""
    staging = load_staging()
    sources = staging.get("sources", [])
    if not sources:
        print("staging is empty")
        return 0

    print(f"staging: {len(sources)} paper(s)\n")
    for s in sources:
        paper_id = s.get("paper_id", "?")
        title = s.get("title", "?")
        n_hyp = len(s.get("hypotheses", []))
        status = s.get("status", "?")
        print(f"  [{status}] {paper_id}")
        print(f"    {title}")
        print(f"    {n_hyp} hypothesis(es)")
        for h in s.get("hypotheses", []):
            hid = h.get("hypothesis_id", "?")
            cls = h.get("classification", "?")
            stmt = h.get("statement", "")[:80]
            print(f"      - {hid} ({cls}): {stmt}")
        print()
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    """Move a staging entry to the main registry."""
    staging = load_staging()
    sources = staging.get("sources", [])

    # Find the entry
    target = None
    target_idx = -1
    for i, s in enumerate(sources):
        if s.get("paper_id") == args.paper_id:
            target = s
            target_idx = i
            break

    if target is None:
        print(f"paper_id not found in staging: {args.paper_id}")
        print("available IDs:", ", ".join(s.get("paper_id", "?") for s in sources))
        return 1

    # Check it's not already in registry
    registry = load_registry()
    csid = target.get("canonical_source_id")
    if csid and find_source(csid, registry):
        print(f"already in registry: {csid}")
        return 1

    # Update status
    target["status"] = "verified"

    # Generate literature note if template exists
    note_path = target.get("note_path")
    if note_path:
        full_note_path = REPOSITORY_ROOT / note_path
        if not full_note_path.exists():
            _generate_note(target, full_note_path)
            print(f"  generated note: {note_path}")

    # Validate the entry in context
    test_registry = json.loads(json.dumps(registry))
    test_registry["sources"].append(target)
    errors = validate_registry(test_registry)
    if errors:
        print("validation errors:")
        for e in errors:
            print(f"  - {e}")
        print("\nfix these before approving, or edit staging.json manually")
        return 1

    # Move to registry
    registry["sources"].append(target)
    REGISTRY_PATH.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"  added to registry: {target.get('paper_id')}")

    # Remove from staging
    del sources[target_idx]
    save_staging(staging)
    print(f"  removed from staging")

    return 0


def _generate_note(entry: dict[str, Any], path: Path) -> None:
    """Generate a minimal literature note from a staging entry."""
    path.parent.mkdir(parents=True, exist_ok=True)

    title = entry.get("title", "Unknown")
    authors = entry.get("authors", [])
    year = entry.get("year", "?")
    csid = entry.get("canonical_source_id", "?")
    source_url = entry.get("source_url", "?")
    tier = entry.get("evidence_tier", "primary_abstract")

    hyp_block = ""
    for i, h in enumerate(entry.get("hypotheses", []), 1):
        stmt = h.get("statement", "")
        cls = h.get("classification", "?")
        hyp_block += f"\n{i}. {stmt}\n   Classification: {cls}.\n"

    content = textwrap.dedent(f"""\
        # {title}

        - **Authors:** {', '.join(authors)}
        - **Year:** {year}
        - **Canonical source ID:** `{csid}`
        - **Source:** [{source_url}]({source_url})
        - **Evidence tier:** `{tier}`
        - **Status:** `verified`

        ## Source-stated finding

        (To be filled after reading the paper.)

        ## Evidence market, asset, and horizon

        - **Market/venue:** Not established from abstract alone.
        - **Assets:** Not established from abstract alone.
        - **Horizon:** Not established from abstract alone.

        ## Caveats

        This entry was generated from the paper abstract by the literature scout.
        Full-text verification is needed before treating any hypothesis as grounded.

        ## Repository mapping

        See `registry.json` for feature mappings.

        ## Extracted testable hypotheses
        {hyp_block}
        ## Unsupported extrapolations

        - Treating abstract-only findings as verified empirical results.
        - Applying the paper's thresholds or execution claims directly.
        - Assuming crypto applicability without testing.

        ## Status

        Verified bibliographic entry via literature scout. Hypotheses are untested
        research ideas from the abstract, not reproduced results.
    """)

    path.write_text(content, encoding="utf-8")


# ── Main ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="literature_scout",
        description="Automated literature scout for hypothesis discovery",
    )
    sub = parser.add_subparsers(dest="command")

    p_search = sub.add_parser("search", help="search papers and stage hypotheses")
    p_search.add_argument(
        "--limit", type=int, default=5,
        help="results per query (default: 5)",
    )
    p_search.add_argument(
        "--year-range", default="2015-",
        help="year filter for search (default: 2015-)",
    )
    p_search.add_argument(
        "--threshold", type=int, default=6,
        help="minimum relevance score 0-10 (default: 6)",
    )

    sub.add_parser("status", help="show staging summary")

    p_approve = sub.add_parser("approve", help="move staging entry to registry")
    p_approve.add_argument("paper_id", help="paper_id to approve")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "search":
            return cmd_search(args)
        elif args.command == "status":
            return cmd_status(args)
        elif args.command == "approve":
            return cmd_approve(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
