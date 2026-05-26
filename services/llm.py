"""LLM interface.

Two backends, picked by what's in .env:

  1. **Vertex AI** (preferred, enterprise-safe) — uses `google-genai` with
     Application Default Credentials. **No JSON key required.** Auth flows from
     `gcloud auth application-default login` on the local machine. Honors org
     policies that disable service-account key creation.
  2. **Gemini AI Studio** (fallback) — uses `GEMINI_API_KEY` via REST.

Departments inject `LLMFn` so the whole cascade stays testable offline.
"""

from __future__ import annotations

import os
from typing import Callable

LLMFn = Callable[[str], str]

_MODEL = "gemini-2.5-pro"


def get_vertex_llm(
    project: str | None = None,
    location: str | None = None,
    model: str = _MODEL,
) -> LLMFn:
    """Vertex AI path. Requires GCP_PROJECT_ID and ADC (see gcloud auth)."""
    project = project or os.environ.get("GCP_PROJECT_ID")
    location = location or os.environ.get("GCP_LOCATION", "global")
    if not project:
        raise RuntimeError(
            "GCP_PROJECT_ID not set — fill .env, then run "
            "`gcloud auth application-default login` for credentials."
        )
    # lazy import so the AI Studio path can run without google-genai installed
    from google import genai

    client = genai.Client(vertexai=True, project=project, location=location)

    def _complete(prompt: str) -> str:
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        return resp.text or ""

    return _complete


def get_studio_llm(
    api_key: str | None = None,
    model: str = _MODEL,
) -> LLMFn:
    """Gemini AI Studio (REST) path. Requires GEMINI_API_KEY."""
    import httpx

    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set — use Vertex (GCP_PROJECT_ID) or add the key."
        )
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )

    def _complete(prompt: str) -> str:
        # API key in a header, not URL — keeps it out of access logs/history.
        resp = httpx.post(
            endpoint,
            headers={"x-goog-api-key": api_key},
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


def get_default_llm() -> LLMFn:
    """Pick Vertex if a GCP project is configured, else AI Studio, else fail."""
    if os.environ.get("GCP_PROJECT_ID"):
        return get_vertex_llm()
    if os.environ.get("GEMINI_API_KEY"):
        return get_studio_llm()
    raise RuntimeError(
        "No LLM configured. Set GCP_PROJECT_ID (Vertex, recommended) or "
        "GEMINI_API_KEY (AI Studio fallback) in .env."
    )
