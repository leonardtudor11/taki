"""Security / Compliance department (Track 3).

Reads the shared bundle, emits a RiskProfile: exposure indicators, reputational
signals, regulatory signals, third-party risk. This department also owns the
guardrail audit of the other departments (wired in the orchestrator).
"""

from __future__ import annotations

from agents.base import GROUNDING_RULE, build_context, parse_into
from agents.schemas import RiskProfile, SharedBundle
from services.llm import LLMFn, get_default_llm

DEPT = "security"

_PROMPT = """You are the Security / Compliance department of an enterprise intelligence org.
From the live web sources below about "{target}", extract risk signals.

SOURCES:
{context}

Return JSON for a RiskProfile with fields:
- exposure_indicators: list of {{text, citations:[{{url, snippet, source_type}}], confidence}}
- reputational_signals: same shape
- regulatory_signals: same shape
- third_party_risk: same shape
- target: "{target}"

{grounding}
"""


def analyze(bundle: SharedBundle, llm: LLMFn | None = None) -> RiskProfile:
    llm = llm or get_default_llm()
    prompt = _PROMPT.format(
        target=bundle.target,
        context=build_context(bundle),
        grounding=GROUNDING_RULE,
    )
    return parse_into(llm(prompt), RiskProfile)
