"""Contradictions agent (V7.23) — surfaces opposing-source claims.

After grounding has cleared all four dept outputs, this agent reads every
surviving claim across the brief and identifies CONTRADICTION PAIRS: two
mutually inconsistent claims about the same axis (uptime, pricing,
compliance, funding, etc.) that came from different sources.

This is the layer that converts a bundle of independent observations
into a genuine cross-source critique — the dept agents each read the
shared bundle and produce *their* take; the contradictions agent reads
*all of them* and asks "do these stories actually line up?"

The agent's prompt forces it to:
  - Cite the EXACT claim texts on both sides (no paraphrasing)
  - Score severity 1-3 (1=minor wording difference, 3=material conflict)
  - Reject sentiment-only contradictions (one Reddit thread loves Supabase,
    another hates it — that's noise, not a contradiction of fact)
  - Reject stale-fact contradictions (a 2023 article vs a 2025 article)

Citations are pulled from the parent claims, not re-generated, so the
contradictions agent CANNOT hallucinate new evidence — it can only
re-frame existing grounded claims.
"""

from __future__ import annotations

import json
from typing import Iterable

from agents.base import parse_into
from agents.schemas import (
    AccountBrief,
    Citation,
    Claim,
    Contradiction,
    MarketingSignal,
    MarketSignal,
    RiskProfile,
)
from services.llm import LLMFn, get_default_llm

DEPT = "contradictions"


def _flatten_claims(
    *sources: AccountBrief | MarketSignal | RiskProfile | MarketingSignal | None,
) -> list[tuple[str, Claim]]:
    """Walk dept outputs into a flat (field_label, claim) list."""
    out: list[tuple[str, Claim]] = []
    for src in sources:
        if src is None:
            continue
        # access fields on the class to avoid the V2.11 deprecation warning
        for field in type(src).model_fields:
            val = getattr(src, field, None)
            if isinstance(val, list):
                for c in val:
                    if isinstance(c, Claim):
                        out.append((field, c))
    return out


def _render_claims_for_prompt(claims: list[tuple[str, Claim]]) -> str:
    """Compact rendering: each claim numbered + tagged with field + first citation URL."""
    blocks = []
    for i, (field, claim) in enumerate(claims):
        first_url = ""
        if claim.citations:
            first_url = claim.citations[0].url or ""
        blocks.append(
            f"[{i}] ({field}) {claim.text}\n    source: {first_url}"
        )
    return "\n".join(blocks)


_PROMPT = """You are reviewing grounded claims about TARGET produced by four
independent research agents (GTM, Finance, Security, Marketing). Each claim
has been pre-verified against the source bundle, so you can trust the text
of every claim as quoted.

Your job: identify CONTRADICTIONS — claim pairs where the two are mutually
inconsistent on the same axis. Return JSON: {"contradictions": [...]}.

VALID contradictions (return these):
  - "industry-leading uptime" vs "10 days of downtime reported"
  - "pricing held flat at $25" vs "pricing raised to $35 this quarter"
  - "HIPAA compliant out of the box" vs "HIPAA only on enterprise tier"
  - "Series C $100M valuation $1B" vs "Series D $500M valuation $5B"
  - "no production outages" vs "us-east-1 prolonged degradation"

INVALID contradictions (DO NOT return):
  - sentiment differences (one positive review, one negative — not a fact conflict)
  - stale fact updates (a 2023 article superseded by a 2025 one — call out as
    update, not contradiction)
  - different aspects of the same fact (one source covers EU pricing, another
    US pricing — both can be true)
  - vague disagreements where neither side cites a specific number/state

For each contradiction:
  - axis:        2-3 word topic (e.g. "uptime", "pricing", "compliance breadth")
  - claim_a:     COPY the exact text of one claim VERBATIM from the list
  - claim_b:     COPY the exact text of the contradicting claim VERBATIM
  - severity:    integer 1-3 (1=phrasing-level, 2=meaningful, 3=material)
  - summary:     one-sentence framing of the tension, neutral

You may return 0-5 contradictions. Quality over quantity — if no genuine
contradiction exists, return {"contradictions": []}. Do not invent claim
text. Do not include citations (we will lift them from the parent claims
ourselves).

TARGET: {target}

CLAIMS:
{claims_block}
"""


def _build_text_to_cites(
    flat: list[tuple[str, Claim]],
) -> dict[str, list[Citation]]:
    """Map claim text → its citations, for re-attaching evidence after the LLM
    references the claim by its exact text."""
    out: dict[str, list[Citation]] = {}
    for _, claim in flat:
        # multiple identical claim texts can exist across depts; concat their cites
        existing = out.setdefault(claim.text, [])
        existing.extend(claim.citations or [])
    return out


def analyze(
    target: str,
    account_brief: AccountBrief | None,
    market_signal: MarketSignal | None,
    risk_profile: RiskProfile | None,
    marketing_signal: MarketingSignal | None = None,
    llm: LLMFn | None = None,
) -> list[Contradiction]:
    """Surface contradictions across the four dept outputs.

    Returns an empty list if the LLM finds none, or on parse failure (this is
    a 'nice to have' layer — never break the cascade for it).
    """
    flat = _flatten_claims(account_brief, market_signal, risk_profile, marketing_signal)
    if len(flat) < 2:
        return []

    llm = llm or get_default_llm()
    # Avoid str.format — the prompt contains literal JSON braces that
    # would clash with format specifiers. Use plain substitution.
    prompt = (
        _PROMPT
        .replace("{target}", target)
        .replace("{claims_block}", _render_claims_for_prompt(flat))
    )

    try:
        raw = llm(prompt)
    except Exception:
        return []

    # Two valid envelopes: {"contradictions": [...]}  OR  [...]
    try:
        data = json.loads(raw)
    except Exception:
        try:
            from agents.base import strip_fences
            data = json.loads(strip_fences(raw))
        except Exception:
            return []

    if isinstance(data, dict):
        raw_list = data.get("contradictions") or []
    elif isinstance(data, list):
        raw_list = data
    else:
        return []
    if not isinstance(raw_list, list):
        return []

    text_to_cites = _build_text_to_cites(flat)
    out: list[Contradiction] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        try:
            c = Contradiction.model_validate(item)
        except Exception:
            continue
        # re-attach citations from the parent claims (LLM only references by text)
        c.citations_a = list(text_to_cites.get(c.claim_a, []))
        c.citations_b = list(text_to_cites.get(c.claim_b, []))
        # drop the contradiction if either side has zero evidence to back it
        if not c.citations_a or not c.citations_b:
            continue
        out.append(c)
    return out
