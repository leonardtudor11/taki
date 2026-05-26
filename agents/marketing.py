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

⚑ DEPTH OVER SURFACE — read this before answering ⚑

For high-barrier B2B sectors — wind energy, infrastructure, manufacturing,
defense, healthcare, regulated industries, professional services — buyers
do NOT decide on copy, voice, or SEO. They decide on:
  • Named past customers and reference projects (with verifiable scale)
  • Quantitative track record (installed capacity, MW, years operating,
    project count, headcount, served countries)
  • Industry-specific certifications and standards (IEC 61400 for wind,
    ISO 9001/14001/27001, sector quality marks, grid-code compliance)
  • Real collaborator network (utilities, OEMs, EPCs, suppliers,
    academic partnerships, government R&D, standards bodies)
  • Trade press, conferences, RFP qualifications, public tender wins

For lower-barrier consumer / SaaS / D2C, weight things like funnels,
SEO copy, social proof, pricing-page clarity HIGHER.

When in doubt about which mode applies, treat as high-barrier — the
expensive mistake is recommending an SEO tweak to a wind-turbine company
that needs reference projects.

Return JSON for a MarketingSignal. Every field below is an ARRAY of claim
objects — even when you only have one observation, wrap it as a one-element
array `[{{...}}]`. Never return a bare object.

A claim object:
  {{
    "text": "...one sentence observation, ideally with named entities + numbers...",
    "citations": [{{"url": "...", "snippet": "verbatim from the source",
                    "source_type": "site"}}],
    "confidence": 0.8
  }}

Fields (use the appropriate lens for the sector — depth vs surface):
- target: "{target}"
- value_proposition:  ARRAY[claim] — what value the FOUNDER's site
                      communicates today. For high-barrier B2B, prioritize
                      quantitative claims (MW installed, headcount, years,
                      named industry served).
- positioning:        ARRAY[claim] — how the founder positions vs the
                      competitor sources. Name competitors + the dimension
                      of comparison (price / capacity / certifications /
                      delivery time / track record).
- brand_voice:        ARRAY[claim] — observed voice on the founder's site.
                      For high-barrier B2B this should be SHORT — note tone
                      but don't pad with copy critique.
- content_gaps:       ARRAY[claim] — MISSING evidence buyers need.
    For high-barrier B2B examples:
      • "no installed-project portfolio — no named utility customers,
        no MW capacity figures, no commissioning dates; buyers in this
        sector use RFPs and pre-qualification — without a public proof
        portfolio, you cannot pass screening"
      • "no IEC 61400-1 / GL Renewables / equivalent certification
        statement on the site"
      • "no public list of standards-body memberships or trade-association
        affiliations (WindEurope, AWEA, sector regulators)"
      • "no published technical white-papers or conference talks — high-
        barrier buyers want to see engineering depth, not marketing"
      • "no named partner network (utilities, OEMs, EPCs, grid operators)"
    For SaaS / D2C examples:
      • "no pricing page with named segments"
      • "no public case studies / G2 reviews"
      • "missing meta description / structured data for SEO"
- channel_signals:    ARRAY[claim] — which channels the founder uses /
                      doesn't. For high-barrier B2B, the channels are
                      RFPs / trade press / conferences / direct outreach
                      to procurement / industry-association presence —
                      NOT Facebook ads. For SaaS, it's the opposite.

If a field has nothing observable, return `[]` — do NOT return null, do
NOT omit the field.

{grounding}

Tone: direct, plain English, no jargon. Specific named entities + numbers
beat generic copy advice every time. Don't recommend SEO/H1-tag fixes for
a wind-turbine company — recommend reference-portfolio publication.
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
