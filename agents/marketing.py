"""Marketing department (V7).

Fourth dept. Same shape as GTM/Finance/Security but a different lens:
positioning, value proposition, brand voice, content gaps, channel signals.

Two prompt variants by cascade mode:

  - self mode: the user's own website + concept is being scraped. The prompt
    asks 'what is THIS BUSINESS saying, where is it weak, what should it
    change' — output is for the founder to act on.
  - target mode: the same lens applied to someone else's site for sales
    intel (how they pitch, what they emphasise) — same schema, different
    framing in the rationale.

Grounding rule applies (every claim cites a snippet that exists in the bundle).
"""

from __future__ import annotations

from agents.base import GROUNDING_RULE, build_context, parse_into
from agents.schemas import CascadeMode, MarketingSignal, SharedBundle
from services.llm import LLMFn, get_default_llm

DEPT = "marketing"


_PROMPT_TARGET = """You are the Marketing department of an enterprise revenue intelligence org.
Read the live-web sources below about "{target}" and extract marketing-relevant signals
about how THEY position themselves.

SOURCES:
{context}

Return JSON for a MarketingSignal with fields:
- value_proposition:  list of {{text, citations:[{{url, snippet, source_type}}], confidence}}
- positioning:        same shape (how they frame themselves vs the market)
- brand_voice:        same shape (tone, vocabulary, persona)
- content_gaps:       same shape (what's missing from their public marketing)
- channel_signals:    same shape (which channels / surfaces they invest in)
- target: "{target}"

{grounding}
"""


_PROMPT_SELF = """You are the Marketing department advising a small business founder.
The sources below were scraped from the founder's OWN website (subject = 'self')
plus optional competitor sites (subject = 'competitor'). The founder runs
"{target}". Be diagnostic and constructive — the output goes to THEM.

BUSINESS CONTEXT:
{business_context}

SOURCES (mixed self + competitor):
{context}

Return JSON for a MarketingSignal with fields:
- value_proposition:  what value the FOUNDER's site actually communicates today
                      (text, citations[...], confidence)
- positioning:        how the founder is positioning vs the competitor sources
- brand_voice:        observed voice on the founder's site (tone, persona, vocabulary)
- content_gaps:       things missing from the founder's marketing that the
                      competitors have or that the founder's stated goal demands.
                      These are the actionable items — call out specifics
                      ("homepage doesn't mention industry use cases", "no pricing
                      page", "no case studies", "missing meta description on /",
                      etc.). Cite a competitor snippet or the founder's own page.
- channel_signals:    which channels the founder is and isn't using
- target: "{target}"

{grounding}

Tone: direct, plain English, no jargon. Each claim should read like a note
from a marketing advisor — observation + (where relevant) implication.
"""


def _business_context(profile_block: str | None) -> str:
    """Render the founder's BusinessProfile for the prompt."""
    return profile_block or "(no extra context provided)"


def analyze(
    bundle: SharedBundle,
    llm: LLMFn | None = None,
    mode: CascadeMode = CascadeMode.TARGET,
    business_context: str = "",
) -> MarketingSignal:
    """Run the marketing analysis. Mode picks the prompt variant."""
    llm = llm or get_default_llm()
    if mode == CascadeMode.SELF:
        prompt = _PROMPT_SELF.format(
            target=bundle.target,
            business_context=_business_context(business_context),
            context=build_context(bundle),
            grounding=GROUNDING_RULE,
        )
    else:
        prompt = _PROMPT_TARGET.format(
            target=bundle.target,
            context=build_context(bundle),
            grounding=GROUNDING_RULE,
        )
    return parse_into(llm(prompt), MarketingSignal)
