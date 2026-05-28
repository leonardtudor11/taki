"""V7.35 — LLM-driven cross-pollination.

Replaces the templated rule-based cross_pollinate (orchestrator.py /
cascade_graph.cross_node) for the cross-talk layer of the cascade.
Reads all 4 dept signals + sector signal + business profile and emits
HandoffMessage + SynergySignal lists whose CONTENT is personalized to
each company — not boilerplate strings that read identically across
Pfizer / Notion / Supabase / Orchid.

Design:
  - One LLM call per cascade
  - Prompt is structured so the LLM gets:
      * target name + industry + stage (business profile)
      * sector signal (pharma/saas/energy/generic buckets w/ counts)
      * each dept's claim texts inline w/ source URLs
  - LLM emits handoffs (from_dept→to_dept w/ message + refs) and
    synergies (text + contributing_depts + citations).
  - Refs MUST come from the cited claim URLs the LLM was shown — we
    don't trust the LLM to invent URLs (citations_only_from_input cap).
  - Hard cap: 6 handoffs, 4 synergies (the dashboard cytoscape arc
    overlap budget; more = visual noise).
  - On any failure (parse / empty / timeout), the caller falls back to
    the templated function so the cascade never ends up with zero
    cross-talk content.
"""

from __future__ import annotations

import json

from agents.base import strip_fences
from agents.schemas import (
    AccountBrief,
    BusinessProfile,
    Citation,
    Claim,
    HandoffMessage,
    MarketSignal,
    MarketingSignal,
    RiskProfile,
    Sector,
    SectorSignal,
    SourceType,
    SynergySignal,
)
from services.llm import LLMFn, get_default_llm

DEPT = "cross_pollinate"

MAX_HANDOFFS  = 6
MAX_SYNERGIES = 4

_DEPT_FIELDS = {
    "gtm":       ["buying_signals", "competitor_moves", "hiring_signals"],
    "finance":   ["pricing_trend", "expansion_contraction", "web_traffic_proxy", "vendor_health_flags"],
    "marketing": ["value_proposition", "positioning", "brand_voice", "content_gaps", "channel_signals"],
    "security":  ["exposure_indicators", "reputational_signals", "regulatory_signals", "third_party_risk"],
}

_PROMPT = """You are a Chief of Staff synthesizing intelligence about "{target}"
across four department analyses. Your job: surface cross-department
HANDOFFS (specific issue dept-A must escalate to dept-B) and
SYNERGIES (combined signals that yield a strategic implication no
single dept could see alone).

BUSINESS CONTEXT:
{profile_block}

SECTOR SIGNAL ({sector}):
{sector_block}

DEPARTMENT FINDINGS (each line: "[dept.field#N] claim text — sources: URL,URL"):
{dept_block}

OUTPUT JSON ONLY:
{{
  "handoffs": [
    {{
      "from_dept": "finance",       // one of: gtm, finance, marketing, security
      "to_dept":   "gtm",
      "message":   "Specific to-the-point cross-talk grounded in the cited claims. 1 sentence. NO generic platitudes.",
      "refs":      ["https://...","https://..."]   // copy from the claims you used; do not invent
    }}
  ],
  "synergies": [
    {{
      "text":               "Synthesis sentence that only makes sense when 2+ dept signals combine. NO templated phrasing.",
      "contributing_depts": ["finance", "security"],
      "citations": [
        {{"url": "https://...", "snippet": "verbatim phrase from the claim text", "source_type": "site|news|review|pricing|jobs|other"}}
      ]
    }}
  ]
}}

Rules:
  - Each handoff/synergy must reference SPECIFIC facts from the
    findings above. If you can't find a specific basis, emit fewer
    entries — empty lists are fine.
  - URLs must come from the source lists you were shown. Inventing
    URLs is forbidden.
  - Cap: up to {max_handoffs} handoffs, up to {max_synergies}
    synergies. Quality over quantity.
  - Use the business industry + stage + sector signal to tune
    relevance: a "growth-stage SaaS" handoff message about pricing
    looks different from a "scale-stage pharma" handoff about
    regulatory submissions.
  - Avoid these stale templates:
      "Pricing change detected — adjust outreach timing/messaging"
      "Reputational signal — frame responsibly, do not weaponize"
      "Hiring expansion — new attack surface / vendors to monitor"
      "Pricing increase coincides with support/reputation complaints"
      "Hiring plus funding/expansion signals a growth account"
    These came from the deterministic predecessor; an LLM run should
    yield insights with the company's own specifics in them.

Output JSON only — no prose, no markdown fences."""


def _claims_of(field_obj, field_name: str) -> list[Claim]:
    val = getattr(field_obj, field_name, None) if field_obj else None
    return val if isinstance(val, list) else []


def _render_dept_block(
    ab: AccountBrief | None,
    ms: MarketSignal | None,
    mk: MarketingSignal | None,
    rp: RiskProfile | None,
) -> str:
    sources = (("gtm", ab), ("finance", ms), ("marketing", mk), ("security", rp))
    lines: list[str] = []
    for dept, obj in sources:
        if not obj:
            continue
        for field in _DEPT_FIELDS[dept]:
            claims = _claims_of(obj, field)
            for i, c in enumerate(claims):
                if not isinstance(c, Claim) or not (c.text or "").strip():
                    continue
                urls = ",".join(
                    (cit.url or "")[:120] for cit in (c.citations or [])
                    if isinstance(cit, Citation) and cit.url
                )
                # Trim claim text to keep prompt budget reasonable across
                # 30-50 claims per cascade.
                txt = (c.text or "").strip()
                if len(txt) > 240:
                    txt = txt[:237] + "..."
                lines.append(
                    f"[{dept}.{field}#{i}] {txt}"
                    + (f" — sources: {urls}" if urls else "")
                )
    return "\n".join(lines) if lines else "(no claims)"


def _render_profile_block(profile: BusinessProfile | None) -> str:
    if not profile:
        return "(no business profile extracted)"
    bits: list[str] = []
    if profile.name:              bits.append(f"name: {profile.name}")
    if profile.industry:          bits.append(f"industry: {profile.industry}")
    if profile.stage:             bits.append(f"stage: {profile.stage}")
    if profile.customer_segment:  bits.append(f"customer: {profile.customer_segment}")
    if profile.goal:              bits.append(f"goal: {profile.goal}")
    if profile.competitor_names:
        bits.append(f"competitors: {', '.join(profile.competitor_names[:6])}")
    return "\n".join(bits) if bits else "(profile fields empty)"


def _render_sector_block(sector: Sector | None, signal: SectorSignal | None) -> str:
    if not sector or not signal:
        return "(no sector pass)"
    out: list[str] = []
    for field in (signal.model_fields or {}):
        val = getattr(signal, field, None)
        if isinstance(val, list):
            out.append(f"{field}: {len(val)} items"
                       + (f" — e.g. {(val[0] if isinstance(val[0], str) else getattr(val[0], 'text', str(val[0])))[:120]}" if val else ""))
    return "\n".join(out) if out else f"({sector.value} signal empty)"


def _filter_refs(refs: list[str], allowed_urls: set[str]) -> list[str]:
    """Keep only URLs the LLM was shown — defence against hallucination."""
    out: list[str] = []
    for u in refs or []:
        if not isinstance(u, str):
            continue
        u = u.strip()
        if u and u in allowed_urls:
            out.append(u)
    return out


def _collect_allowed_urls(ab, ms, mk, rp) -> set[str]:
    urls: set[str] = set()
    for dept, obj in (("gtm", ab), ("finance", ms), ("marketing", mk), ("security", rp)):
        if not obj:
            continue
        for field in _DEPT_FIELDS[dept]:
            for c in _claims_of(obj, field):
                for cit in (c.citations or []):
                    if isinstance(cit, Citation) and cit.url:
                        urls.add(cit.url)
    return urls


def analyze(
    account_brief: AccountBrief | None,
    market_signal: MarketSignal | None,
    marketing_signal: MarketingSignal | None,
    risk_profile: RiskProfile | None,
    business_profile: BusinessProfile | None,
    sector: Sector | None,
    sector_signal: SectorSignal | None,
    target: str,
    llm: LLMFn | None = None,
) -> tuple[list[HandoffMessage], list[SynergySignal]]:
    """LLM-driven cross-pollination.

    Returns (handoffs, synergies) — possibly empty lists if the LLM
    couldn't find grounded cross-talk. Caller falls back to the
    templated cross_pollinate on empty results.

    Never raises — parsing/LLM failures degrade to ([], []) and the
    caller's fallback kicks in.
    """
    # Need at least one of the four dept signals to have anything to talk about.
    if not any((account_brief, market_signal, marketing_signal, risk_profile)):
        return ([], [])

    llm = llm or get_default_llm()
    allowed_urls = _collect_allowed_urls(
        account_brief, market_signal, marketing_signal, risk_profile,
    )

    prompt = _PROMPT.format(
        target=target,
        profile_block=_render_profile_block(business_profile),
        sector=sector.value if sector else "none",
        sector_block=_render_sector_block(sector, sector_signal),
        dept_block=_render_dept_block(
            account_brief, market_signal, marketing_signal, risk_profile,
        ),
        max_handoffs=MAX_HANDOFFS,
        max_synergies=MAX_SYNERGIES,
    )
    try:
        raw = llm(prompt)
        obj = json.loads(strip_fences(raw))
    except Exception:
        return ([], [])

    # V7.47 — same list-wrap shape that V7.46 hit in parse_into. Some LLM
    # responses arrive as [{...}] instead of {...}; unwrap before the
    # dict-shape gate. Without this, valid cross-talk gets silently
    # dropped to templated fallback (observed on the Notion run where
    # cross_pollinate_done events recorded source="fallback").
    if isinstance(obj, list) and len(obj) == 1 and isinstance(obj[0], dict):
        obj = obj[0]

    if not isinstance(obj, dict):
        return ([], [])

    handoffs: list[HandoffMessage] = []
    for entry in (obj.get("handoffs") or [])[: MAX_HANDOFFS * 2]:
        if not isinstance(entry, dict):
            continue
        # Refs must be URLs the LLM was shown; otherwise drop.
        entry["refs"] = _filter_refs(entry.get("refs") or [], allowed_urls)
        try:
            h = HandoffMessage.model_validate(entry)
        except Exception:
            continue
        if not (h.message or "").strip() or not h.from_dept or not h.to_dept:
            continue
        if h.from_dept == h.to_dept:
            continue
        handoffs.append(h)
        if len(handoffs) >= MAX_HANDOFFS:
            break

    synergies: list[SynergySignal] = []
    for entry in (obj.get("synergies") or [])[: MAX_SYNERGIES * 2]:
        if not isinstance(entry, dict):
            continue
        # Citation URLs must also come from the shown set.
        clean_citations: list[dict] = []
        for cit in (entry.get("citations") or []):
            if not isinstance(cit, dict):
                continue
            url = (cit.get("url") or "").strip()
            if url and url in allowed_urls:
                clean_citations.append({
                    "url": url,
                    "snippet": (cit.get("snippet") or "")[:300],
                    "source_type": cit.get("source_type") or SourceType.OTHER.value,
                })
        entry["citations"] = clean_citations
        try:
            s = SynergySignal.model_validate(entry)
        except Exception:
            continue
        if not (s.text or "").strip() or len(s.contributing_depts) < 2:
            continue
        synergies.append(s)
        if len(synergies) >= MAX_SYNERGIES:
            break

    return (handoffs, synergies)
