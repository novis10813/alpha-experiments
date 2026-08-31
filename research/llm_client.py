"""Minimal OpenRouter chat completion client.

Uses only stdlib ``urllib`` and ``json``.  Shares the same
``OPENROUTER_API_KEY`` environment variable used by the evolution pipeline.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


_DEFAULT_API_BASE = "https://openrouter.ai/api/v1"
_DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 5  # seconds


def _api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Export it before running the scout."
        )
    return key


def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str = _DEFAULT_MODEL,
    temperature: float = 0.4,
    max_tokens: int = 4096,
    api_base: str = _DEFAULT_API_BASE,
) -> str:
    """Send a chat completion request and return the assistant content.

    Retries on HTTP 429 with exponential backoff.  Raises on persistent
    failure or missing content.
    """
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
    ).encode()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_api_key()}",
    }

    url = f"{api_base.rstrip('/')}/chat/completions"
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                body: dict[str, Any] = json.loads(resp.read())
            choices = body.get("choices")
            if not choices:
                raise RuntimeError(f"empty choices in LLM response: {body}")
            content = choices[0].get("message", {}).get("content", "").strip()
            if not content:
                raise RuntimeError(f"empty content in LLM response: {body}")
            return content
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                print(f"  [llm] 429 rate-limited, retrying in {delay}s …")
                time.sleep(delay)
                continue
            raise
        except urllib.error.URLError as exc:
            last_error = exc
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            print(f"  [llm] network error ({exc.reason}), retrying in {delay}s …")
            time.sleep(delay)
            continue

    raise RuntimeError(f"LLM request failed after {_MAX_RETRIES} retries") from last_error
