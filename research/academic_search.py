"""Semantic Scholar API client for academic paper search.

Uses only stdlib ``urllib`` and ``json``.  Respects the Semantic Scholar
unauthenticated rate limit (1 request per second) by default.
An optional ``S2_API_KEY`` environment variable enables higher throughput.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any


_BASE_URL = "https://api.semanticscholar.org/graph/v1"
_SEARCH_FIELDS = "title,abstract,externalIds,year,authors,url"
_MIN_DELAY = 1.05  # seconds between unauthenticated requests


@dataclass
class PaperResult:
    """Minimal paper metadata returned by a search."""

    paper_id: str  # Semantic Scholar corpus ID
    title: str
    abstract: str
    year: int | None
    authors: list[str]
    doi: str | None
    arxiv_id: str | None
    url: str | None

    def canonical_ids(self) -> list[str]:
        """Return all identifier forms for dedup."""
        ids: list[str] = []
        if self.doi:
            ids.append(f"doi:{self.doi.lower()}")
        if self.arxiv_id:
            ids.append(f"arxiv:{self.arxiv_id}")
        return ids


def _headers() -> dict[str, str]:
    headers: dict[str, str] = {
        "User-Agent": "alpha-experiments-literature-scout/0.1",
    }
    key = os.environ.get("S2_API_KEY", "").strip()
    if key:
        headers["x-api-key"] = key
    return headers


def _get_json(url: str) -> dict[str, Any] | None:
    """Fetch JSON from a URL, returning None on 404/429/network errors."""
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            # Rate limited — wait and retry once
            print(f"  [s2] 429 rate-limited, waiting 5s …")
            time.sleep(5)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read())
            except Exception:
                return None
        if exc.code in (404, 400):
            return None
        print(f"  [s2] HTTP {exc.code} for {url}")
        return None
    except urllib.error.URLError as exc:
        print(f"  [s2] network error: {exc.reason}")
        return None


def _parse_paper(raw: dict[str, Any]) -> PaperResult | None:
    """Parse a single paper from the Semantic Scholar response."""
    title = raw.get("title") or ""
    abstract = raw.get("abstract") or ""
    if not title or not abstract:
        return None  # skip papers without abstracts

    ext = raw.get("externalIds") or {}
    authors_raw = raw.get("authors") or []

    return PaperResult(
        paper_id=raw.get("paperId", ""),
        title=title.strip(),
        abstract=abstract.strip(),
        year=raw.get("year"),
        authors=[a.get("name", "") for a in authors_raw if a.get("name")],
        doi=ext.get("DOI"),
        arxiv_id=ext.get("ArXiv"),
        url=raw.get("url"),
    )


def search_papers(
    query: str,
    *,
    limit: int = 5,
    year_range: str | None = None,
) -> list[PaperResult]:
    """Search Semantic Scholar and return papers with abstracts.

    Parameters
    ----------
    query
        Free-text search query.
    limit
        Maximum number of results to return per query.
    year_range
        Optional year filter, e.g. ``"2018-"`` or ``"2015-2024"``.
    """
    params: dict[str, str] = {
        "query": query,
        "limit": str(min(limit, 20)),
        "fields": _SEARCH_FIELDS,
    }
    if year_range:
        params["year"] = year_range

    url = f"{_BASE_URL}/paper/search?{urllib.parse.urlencode(params)}"
    data = _get_json(url)
    if not data:
        return []

    results: list[PaperResult] = []
    for raw in data.get("data", []):
        paper = _parse_paper(raw)
        if paper:
            results.append(paper)

    return results


def search_multiple(
    queries: list[str],
    *,
    limit_per_query: int = 5,
    year_range: str | None = None,
) -> list[PaperResult]:
    """Run multiple queries sequentially with rate limiting and dedup."""
    seen_ids: set[str] = set()
    results: list[PaperResult] = []

    for i, query in enumerate(queries):
        if i > 0:
            time.sleep(_MIN_DELAY)

        print(f"  [s2] searching: {query!r}")
        papers = search_papers(query, limit=limit_per_query, year_range=year_range)

        for paper in papers:
            # dedup by Semantic Scholar paper ID
            if paper.paper_id in seen_ids:
                continue
            seen_ids.add(paper.paper_id)
            results.append(paper)

        print(f"  [s2]   → {len(papers)} results ({len(results)} total unique)")

    return results
