"""LLM interface.

Departments depend on an injected `LLMFn` (prompt -> raw JSON text), so they are
fully testable offline with a fake. The default implementation calls the Gemini
REST API and needs GEMINI_API_KEY; it is wired but only runs once keys are set.
"""

from __future__ import annotations

import os
from typing import Callable

import httpx

LLMFn = Callable[[str], str]

_MODEL = "gemini-2.5-pro"
_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_MODEL}:generateContent"
)


def get_default_llm() -> LLMFn:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY not set — inject a fake LLMFn for tests, or add the "
            "key to .env for live runs."
        )

    def _complete(prompt: str) -> str:
        resp = httpx.post(
            _ENDPOINT,
            params={"key": key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"response_mime_type": "application/json"},
            },
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    return _complete
