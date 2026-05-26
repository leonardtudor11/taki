"""Strategy department — the 'Chief of Staff' agent.

Synthesizes the grounded outputs of GTM, Finance, and Security (plus their
synergy signals and dept-to-dept handoffs) into a single StrategicPlan:

  - headline                 one-sentence framing
  - narrative                2-3 paragraph executive write-up
  - icp_fit + rationale      coarse high/medium/low fit ranking
  - deal_size_estimate       "$Xk-$Yk ARR" range with basis
  - urgency                  act-this-Q / act-this-half / monitor
  - recommended_plays        3-5 prioritized actions, dept-tagged, cited
  - open_questions           gaps the next research pass should fill

The prompt forces every recommended play to cite at least one snippet that
appears verbatim somewhere in the dept outputs above (citation chain back
through the dept claims, which themselves chain back to the SharedBundle).
The grounding guard at the orchestrator level enforces this on the claims;
strategic-plan citations are advisory.
"""

from __future__ import annotations

import json

from agents.base import strip_fences
from agents.schemas import (
    AccountBrief,
    BusinessProfile,
    CascadeMode,
    HandoffMessage,
    MarketingSignal,
    MarketSignal,
    RiskProfile,
    StrategicPlan,
    SynergySignal,
)
from services.llm import LLMFn, get_default_llm

DEPT = "strategy"


def _render_dept(label: str, claims_by_field: dict[str, list]) -> str:
    """Compact text rendering of a dept output for prompt consumption."""
    out: list[str] = [f"## {label}"]
    for field, claims in claims_by_field.items():
        if not claims:
            continue
        out.append(f"  {field}:")
        for c in claims:
            cites = ", ".join(
                f"[{cit.url}]" for cit in (c.citations or [])
            ) or "(no cite)"
            out.append(f"    - {c.text} {cites}")
    return "\n".join(out)


def _render_synergies(synergies: list[SynergySignal]) -> str:
    if not synergies:
        return "  (none)"
    rows = []
    for s in synergies:
        depts = " + ".join(s.contributing_depts or [])
        rows.append(f"  - [{depts}] {s.text}")
    return "\n".join(rows)


def _render_handoffs(handoffs: list[HandoffMessage]) -> str:
    if not handoffs:
        return "  (none)"
    return "\n".join(
        f"  - {h.from_dept.upper()} → {h.to_dept.upper()}: {h.message}"
        for h in handoffs
    )


_PROMPT_TARGET = """You are the Chief of Staff for an enterprise revenue intelligence org.
Three department agents produced GROUNDED signals about target "{target}".
Your job is to synthesize them into ONE strategic plan a CRO could act on
this week — not a summary of signals, an actual plan.

EVIDENCE — dept signals
{gtm_block}

{finance_block}

{security_block}

CROSS-DEPT SYNERGIES
{synergies_block}

CROSS-DEPT HANDOFFS
{handoffs_block}

Return JSON for a StrategicPlan with these fields:

- target: "{target}"
- headline: one sentence, sharp, no hedging. The "so what".
- narrative: 2-3 paragraphs. Paragraph 1: what's the deal here (story).
  Paragraph 2: why now (urgency / timing signals). Paragraph 3: where the
  risk lives (compliance / reputation / vendor / pricing pressure).
- icp_fit: "high" | "medium" | "low"
- icp_rationale: 1-2 sentences tying to specific evidence.
- deal_size_estimate: e.g. "$50k-$200k ARR" — use signals (employee count
  proxies, pricing tier, market segment) to bound it. If unknown, say so.
- deal_size_rationale: how you arrived at that range.
- urgency: "act this quarter" | "act this half" | "monitor"
- urgency_rationale: 1 sentence.
- recommended_plays: 3 to 5 entries. Each is JSON {{
      "text": "one concrete action a seller / CSM / GRC owner can do",
      "priority": 1-5  (1 = urgent, 5 = later),
      "timeframe": "this week" | "30 days" | "this quarter" | "this half",
      "owners": ["gtm" | "finance" | "security"]  (one or more),
      "rationale": "why this play, tied to a specific signal",
      "citations": [{{"url": "...", "snippet": "verbatim snippet from a dept claim above", "source_type": "site"}}]
  }}
  Order plays by priority (1 first). Span owners across depts where the
  evidence supports it — this is what a real cross-functional plan looks
  like.
- open_questions: 3-5 short strings — concrete things the NEXT research
  pass should answer (e.g. "Confirm ARR tier from recent earnings",
  "Verify executive sponsor for the security buy"). These can be uncited
  (they're gaps).

Constraints:
- Every recommended play MUST cite at least one snippet that appears
  verbatim in the dept signals above. Do not invent citations.
- Do not include any field other than the ones listed.
- Output JSON only. No prose around the JSON.
"""


_PROMPT_SELF = """You are the Chief of Staff advising a small business owner directly.
The four departments below produced GROUNDED signals about THEIR OWN business
"{target}" (and optionally some named competitors). Your job is to synthesize
them into ONE actionable plan the founder can execute starting THIS WEEK.

BUSINESS CONTEXT (from the founder):
{business_context}

EVIDENCE — dept signals
{marketing_block}

{gtm_block}

{finance_block}

{security_block}

CROSS-DEPT SYNERGIES
{synergies_block}

CROSS-DEPT HANDOFFS
{handoffs_block}

Return JSON for a StrategicPlan with these fields:

- target: "{target}"
- headline: one sharp sentence answering "what's the single most important
  move for this founder right now?". No hedging. Speak to them ('you').
- narrative: 2-3 paragraphs. Paragraph 1: what's the current state of their
  business based on the evidence. Paragraph 2: what's the biggest opportunity
  and why now. Paragraph 3: what's the biggest risk and how to mitigate it.
  Write FOR the founder ('you', 'your business'), not about them.
- icp_fit: "high" | "medium" | "low" — how well-defined is their target
  customer based on the evidence on their site? high = clear, low = unclear.
- icp_rationale: 1-2 sentences referencing specific signals.
- deal_size_estimate: their plausible average deal size or LTV given pricing
  page + market segment signals — e.g. "$50-$200/mo per customer" or "$5k-$20k
  one-off projects". Be honest if the evidence doesn't support a tight range.
- deal_size_rationale: how you bounded it.
- urgency: "act this week" | "act this month" | "act this quarter"
- urgency_rationale: 1 sentence — what makes the timing matter.
- recommended_plays: 3 to 5 entries. Each is JSON {{
      "text": "ONE concrete action the founder can DO this week or month",
      "priority": 1-5  (1 = urgent, 5 = later),
      "timeframe": "this week" | "this month" | "this quarter",
      "owners": ["marketing" | "gtm" | "finance" | "security"],
      "rationale": "why this play, tied to a specific signal",
      "citations": [{{"url": "...", "snippet": "verbatim snippet from a dept claim above", "source_type": "site"}}]
  }}
  ⚑ SECTOR-AWARE PLAY SELECTION ⚑
  Match the plays to the buyer's actual decision criteria. Look at the
  founder's stated industry + the dept signals to infer sector type:

  HIGH-BARRIER B2B (wind energy, infrastructure, manufacturing, defense,
  healthcare, regulated industries, professional services, enterprise
  procurement-led deals) — buyers decide on PROOF and RELATIONSHIPS,
  not marketing copy. Strong plays look like:
   - "Publish a reference portfolio page with 5+ installed projects,
     each with named utility/municipal customer, MW capacity, and
     commissioning year. Without this you cannot pass RFP pre-qualification."
   - "Begin IEC 61400-1 (or sector-equivalent) certification track —
     list target standards publicly so procurement reviewers see the
     compliance trajectory before they ask."
   - "Join WindEurope / AWEA / relevant industry body and add the
     membership badge — absence of trade-association presence is a
     vendor-screening red flag in this sector."
   - "Co-author a case study with [named utility/EPC from the dept
     signals] from the recent deployment; route through their PR for
     joint distribution. Joint press = third-party validation."
   - "Submit a paper to WindEurope Annual Event 2026 (or the equivalent
     industry conference) — visibility there converts to RFP invites."
   - "Open named-partnership outreach to a tier-1 OEM / EPC; absence
     of a partner network is the #1 RFP rejection reason for new entrants."
  AVOID for high-barrier B2B: SEO fixes, H1 tweaks, ad-channel
  suggestions, social-media calendar advice, generic 'improve your
  copy'. Those will lose the founder's trust — they signal the tool
  doesn't understand the sector.

  LOWER-BARRIER (SaaS / D2C / consumer / freemium) — the OPPOSITE.
  Buyers decide on funnel clarity, pricing transparency, social proof,
  product-led signals. Strong plays:
   - "Add a pricing page that names the top 3 customer segments."
   - "Publish 3-5 G2 / Trustpilot case studies with named buyers."
   - "Stand up a GDPR-aware cookie banner + DPA download before EU launch."

  When in doubt about sector, treat as HIGH-BARRIER — the expensive
  mistake is recommending an SEO tweak to a wind-turbine company that
  needs reference projects.

  Order by priority (1 first). Span dept owners so the founder sees this
  is cross-functional, not just marketing.

- open_questions: 3-5 short strings — concrete things the founder should
  research next (or what more context Taki should be re-run with).
  For high-barrier B2B, examples:
   - "Pull the references / projects pages of [competitor X] to compare
     installed-capacity figures and named utility customers."
   - "Confirm the founder's existing pilot installations — if any —
     so the reference-portfolio play has substrate to publish from."
   - "Verify what IEC / GL / sector certifications the founder already
     holds vs. what is still in flight."
  For SaaS/D2C examples:
   - "Pull pricing pages of [competitor X] for direct comparison."
   - "Confirm whether your stripe/billing flow is PCI-compliant before scale."

Constraints:
- Every recommended play MUST cite at least one snippet that appears
  verbatim in the dept signals above. Do not invent citations.
- Speak FOR the founder — 'you', 'your business' — not 'the target'.
- Be specific. Generic advice ("improve your marketing") is not acceptable.
- Name entities and numbers where the dept signals provide them — buyers
  remember "we installed 12 MW with EDP in 2024", not "we provide
  premium service".
- Output JSON only. No prose around the JSON.
"""


def _render_business_context(profile: BusinessProfile | None) -> str:
    """Plain-text dump of a BusinessProfile for the prompt context."""
    if not profile:
        return "(no founder-provided business context)"
    parts = [
        f"name:      {profile.name}",
        f"url:       {profile.url}",
        f"industry:  {profile.industry or '—'}",
        f"stage:     {profile.stage.value}",
        f"goal:      {profile.goal or '—'}",
        f"customer:  {profile.customer_segment or '—'}",
    ]
    if profile.competitor_names or profile.competitor_urls:
        names = profile.competitor_names or [u for u in profile.competitor_urls]
        parts.append(f"known competitors: {', '.join(names)}")
    return "\n".join(parts)


def analyze(
    target: str,
    account_brief: AccountBrief,
    market_signal: MarketSignal,
    risk_profile: RiskProfile,
    synergies: list[SynergySignal],
    handoffs: list[HandoffMessage],
    llm: LLMFn | None = None,
    mode: CascadeMode = CascadeMode.TARGET,
    business_profile: BusinessProfile | None = None,
    marketing_signal: MarketingSignal | None = None,
) -> StrategicPlan:
    """Run the strategy synthesis. Pure LLM call — no I/O, no scraping.

    `mode` picks the prompt variant:
      - target: classic — analyse someone else as a sales target.
      - self:   advise the founder of THEIR OWN business.

    The marketing dept output is included when present (V7).
    """
    llm = llm or get_default_llm()
    gtm_block = _render_dept("GTM signals", {
        "buying_signals": account_brief.buying_signals,
        "competitor_moves": account_brief.competitor_moves,
        "hiring_signals": account_brief.hiring_signals,
    })
    finance_block = _render_dept("FINANCE signals", {
        "pricing_trend": market_signal.pricing_trend,
        "expansion_contraction": market_signal.expansion_contraction,
        "web_traffic_proxy": market_signal.web_traffic_proxy,
        "vendor_health_flags": market_signal.vendor_health_flags,
    })
    security_block = _render_dept("SECURITY signals", {
        "exposure_indicators": risk_profile.exposure_indicators,
        "reputational_signals": risk_profile.reputational_signals,
        "regulatory_signals": risk_profile.regulatory_signals,
        "third_party_risk": risk_profile.third_party_risk,
    })
    marketing_block = _render_dept("MARKETING signals", {
        "value_proposition": marketing_signal.value_proposition if marketing_signal else [],
        "positioning":       marketing_signal.positioning       if marketing_signal else [],
        "brand_voice":       marketing_signal.brand_voice       if marketing_signal else [],
        "content_gaps":      marketing_signal.content_gaps      if marketing_signal else [],
        "channel_signals":   marketing_signal.channel_signals   if marketing_signal else [],
    }) if marketing_signal else "## MARKETING signals\n  (marketing dept did not produce signals)"

    if mode == CascadeMode.SELF:
        prompt = _PROMPT_SELF.format(
            target=target,
            business_context=_render_business_context(business_profile),
            marketing_block=marketing_block,
            gtm_block=gtm_block,
            finance_block=finance_block,
            security_block=security_block,
            synergies_block=_render_synergies(synergies),
            handoffs_block=_render_handoffs(handoffs),
        )
    else:
        prompt = _PROMPT_TARGET.format(
            target=target,
            gtm_block=gtm_block,
            finance_block=finance_block,
            security_block=security_block,
            synergies_block=_render_synergies(synergies),
            handoffs_block=_render_handoffs(handoffs),
        )
    raw = llm(prompt)
    data = json.loads(strip_fences(raw))
    # ensure target is preserved even if LLM omits it
    data.setdefault("target", target)
    return StrategicPlan.model_validate(data)
