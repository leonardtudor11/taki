"""Finance / Market department (Track 2).

Reads the shared bundle, emits a MarketSignal: pricing trend, expansion/
contraction (job-posts as alt-data), web-traffic proxy, vendor-health flags.
"""

from __future__ import annotations

from agents.base import GROUNDING_RULE, build_context, parse_into
from agents.schemas import MarketSignal, SharedBundle
from services.llm import LLMFn, get_default_llm

DEPT = "finance"

_PROMPT = """You are the Finance / Market department of an enterprise intelligence org.
From the live web sources below about "{target}", extract financial/market signals.

SOURCES:
{context}

Return JSON for a MarketSignal with fields:
- pricing_trend: list of {{text, citations:[{{url, snippet, source_type}}], confidence}}
- expansion_contraction: same shape (treat hiring as alt-data)
- web_traffic_proxy: same shape
- vendor_health_flags: same shape
- target: "{target}"

{grounding}
"""


def analyze(bundle: SharedBundle, llm: LLMFn | None = None) -> MarketSignal:
    llm = llm or get_default_llm()
    prompt = _PROMPT.format(
        target=bundle.target,
        context=build_context(bundle),
        grounding=GROUNDING_RULE,
    )
    return parse_into(llm(prompt), MarketSignal)
