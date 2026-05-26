"""Revenue / GTM department (Track 1).

Reads the shared bundle, emits an AccountBrief: buying signals, competitor
moves, hiring signals, and a recommended outreach angle — all grounded.
"""

from __future__ import annotations

from agents.base import GROUNDING_RULE, build_context, parse_into
from agents.schemas import AccountBrief, SharedBundle
from services.llm import LLMFn, get_default_llm

DEPT = "gtm"

_PROMPT = """You are the Revenue / GTM department of an enterprise intelligence org.
From the live web sources below about "{target}", extract revenue-relevant signals.

SOURCES:
{context}

Return JSON for an AccountBrief with fields:
- buying_signals: list of {{text, citations:[{{url, snippet, source_type}}], confidence}}
- competitor_moves: same shape
- hiring_signals: same shape
- outreach_angle: one concise sentence a seller could open with
- target: "{target}"

{grounding}
"""


def analyze(bundle: SharedBundle, llm: LLMFn | None = None) -> AccountBrief:
    llm = llm or get_default_llm()
    prompt = _PROMPT.format(
        target=bundle.target,
        context=build_context(bundle),
        grounding=GROUNDING_RULE,
    )
    return parse_into(llm(prompt), AccountBrief)
