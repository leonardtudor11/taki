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
    HandoffMessage,
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


_PROMPT = """You are the Chief of Staff for an enterprise revenue intelligence org.
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


def analyze(
    target: str,
    account_brief: AccountBrief,
    market_signal: MarketSignal,
    risk_profile: RiskProfile,
    synergies: list[SynergySignal],
    handoffs: list[HandoffMessage],
    llm: LLMFn | None = None,
) -> StrategicPlan:
    """Run the strategy synthesis. Pure LLM call — no I/O, no scraping.

    Returns a StrategicPlan even on schema-validation failure (Pydantic
    raises in that case, which is the right behaviour — the grounding guard
    won't be able to repair a malformed plan, so loud failure is correct).
    """
    llm = llm or get_default_llm()
    prompt = _PROMPT.format(
        target=target,
        gtm_block=_render_dept("GTM signals", {
            "buying_signals": account_brief.buying_signals,
            "competitor_moves": account_brief.competitor_moves,
            "hiring_signals": account_brief.hiring_signals,
        }),
        finance_block=_render_dept("FINANCE signals", {
            "pricing_trend": market_signal.pricing_trend,
            "expansion_contraction": market_signal.expansion_contraction,
            "web_traffic_proxy": market_signal.web_traffic_proxy,
            "vendor_health_flags": market_signal.vendor_health_flags,
        }),
        security_block=_render_dept("SECURITY signals", {
            "exposure_indicators": risk_profile.exposure_indicators,
            "reputational_signals": risk_profile.reputational_signals,
            "regulatory_signals": risk_profile.regulatory_signals,
            "third_party_risk": risk_profile.third_party_risk,
        }),
        synergies_block=_render_synergies(synergies),
        handoffs_block=_render_handoffs(handoffs),
    )
    raw = llm(prompt)
    data = json.loads(strip_fences(raw))
    # ensure target is preserved even if LLM omits it
    data.setdefault("target", target)
    return StrategicPlan.model_validate(data)
