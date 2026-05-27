"""LangGraph-backed cascade (V2).

Same CascadeBrief output as the legacy sequential orchestrator, but topology
is now an explicit `langgraph.StateGraph`:

    START
      ▼
    pii_redact ──► leak_filter
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
       gtm         finance        security      (parallel dept fan-out)
        └─────────────┼─────────────┘
                      ▼
                  grounding
                      ▼
              cross_pollinate
                      ▼
                  assemble ──► END

Every node may emit `dict` events through an optional callback; the live
entrypoint (`run.py`) wires those events to `data/<slug>/events.jsonl` so the
dashboard can replay the cascade unfolding (V3.2). The dept LLMs are
closure-bound when the graph is compiled, so the cascade stays fully testable
offline (inject fake LLMs, same as the legacy orchestrator).
"""

from __future__ import annotations

import json
import operator
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Callable, TypedDict

from agents import cross_pollinate_llm as cross_pollinate_llm_agent  # V7.35
from agents import expert_quotes as expert_quotes_agent  # V7.34
from agents import finance as finance_agent
from agents import gtm as gtm_agent
from agents import contradictions as contradictions_agent
from agents import marketing as marketing_agent
from agents import pestle as pestle_agent
from agents import porter as porter_agent
from agents import profile as profile_agent  # V7.28
from agents import sector as sector_agent    # V7.29
from agents import security as security_agent
from agents import strategy as strategy_agent
from agents import swot as swot_agent
from agents.schemas import (
    AccountBrief,
    BundleStats,
    BusinessProfile,
    CascadeBrief,
    CascadeMode,
    Citation,
    Claim,
    Contradiction,
    EnergySignal,
    ExpertQuote,
    FiveForces,
    GenericSignal,
    GuardrailReport,
    HandoffMessage,
    MarketSignal,
    MarketingSignal,
    PharmaSignal,
    Pestle,
    RiskProfile,
    SaasSignal,
    Sector,
    SectorSignal,
    SharedBundle,
    SourceItem,
    SourceSubject,
    StrategicPlan,
    Swot,
    SynergySignal,
)
from guardrails import grounding, leak, pii
from services.llm import LLMFn

EventCallback = Callable[[dict], None]


# claim-bearing fields per department, for per-field grounding (kept in sync
# with the legacy orchestrator's _DEPT_FIELDS so behaviour is byte-identical).
_DEPT_FIELDS = {
    AccountBrief: ["buying_signals", "competitor_moves", "hiring_signals"],
    MarketSignal: [
        "pricing_trend",
        "expansion_contraction",
        "web_traffic_proxy",
        "vendor_health_flags",
    ],
    MarketingSignal: [
        "value_proposition",
        "positioning",
        "brand_voice",
        "content_gaps",
        "channel_signals",
    ],
    RiskProfile: [
        "exposure_indicators",
        "reputational_signals",
        "regulatory_signals",
        "third_party_risk",
    ],
}


class CascadeState(TypedDict, total=False):
    """LangGraph state. Reducer-merged keys use `operator.add`."""

    bundle: SharedBundle
    clean: SharedBundle
    pii_count: int
    leak_flags: list[str]
    account_brief: AccountBrief
    market_signal: MarketSignal
    marketing_signal: MarketingSignal
    risk_profile: RiskProfile
    dropped: Annotated[list[str], operator.add]
    synergies: list[SynergySignal]
    handoffs: list[HandoffMessage]
    strategic_plan: StrategicPlan
    contradictions: list[Contradiction]
    five_forces: FiveForces
    swot: Swot
    pestle: Pestle
    events: Annotated[list[dict], operator.add]
    brief: CascadeBrief
    # V7 — self-mode inputs (closure-bound at build_graph; not in invoke state
    # because LLMs are still closure-bound. Profile is kept here so prompts
    # downstream can read it.)
    business_profile: BusinessProfile
    mode: CascadeMode
    # V7.29 — sector-conditional sub-pipeline. sector_pass picks one of
    # 4 sector branches based on business_profile.industry and produces
    # a SectorSignal subclass — pharma / saas / energy / generic.
    sector: Sector
    sector_signal: SectorSignal
    # V7.34 — named-expert verbatim quotes extracted from the bundle.
    expert_quotes: list[ExpertQuote]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_subpath(url: str) -> bool:
    """True when URL has a path beyond the site root ('' or '/').

    Used by _compute_bundle_stats to detect V7.31 sub-page discovery
    hits — root URLs are user-supplied seeds, paths beyond root came
    from the concept-walk helper.
    """
    if not url:
        return False
    try:
        from urllib.parse import urlparse
        path = (urlparse(url).path or "").strip()
    except Exception:
        return False
    return path not in ("", "/")


def _compute_bundle_stats(
    bundle: SharedBundle | None,
    expert_quote_count: int = 0,
) -> BundleStats:
    """V7.37 — per-cascade bundle quality snapshot.

    Tier counts use services.brightdata.classify_url. Sub-page count
    detects URLs with a non-root path that came from the
    discover_subpages helper (heuristic: subject=TARGET, source_type=SITE,
    URL has > 1 path segment). Chrome fallback count detects Wikipedia
    + Wayback Machine fallbacks from V7.30.
    """
    stats = BundleStats()
    if not bundle or not bundle.sources:
        stats.expert_quote_count = expert_quote_count
        return stats

    # Local import — services.brightdata pulls httpx + tenacity; keep the
    # cascade_graph import surface minimal for tests that don't need BD.
    from services.brightdata import classify_url

    by_tier: dict[str, int] = {}
    by_subject: dict[str, int] = {}
    by_source_type: dict[str, int] = {}
    expanded = 0
    chrome = 0

    for src in bundle.sources:
        if not isinstance(src, SourceItem):
            continue
        url = src.url or ""
        # tier
        tier = classify_url(url) if url else "T0"
        by_tier[tier] = by_tier.get(tier, 0) + 1
        # subject
        subj = src.subject.value if hasattr(src.subject, "value") else str(src.subject)
        by_subject[subj] = by_subject.get(subj, 0) + 1
        # source_type
        st = src.source_type.value if hasattr(src.source_type, "value") else str(src.source_type)
        by_source_type[st] = by_source_type.get(st, 0) + 1
        # chrome fallback heuristic — V7.30 inserts these via
        # fetch_js_chrome_fallbacks with wikipedia.org/wiki or
        # web.archive.org hosts.
        if "en.wikipedia.org/wiki" in url or "web.archive.org/web/" in url:
            chrome += 1
        # sub-page heuristic — V7.31 inserts SITE-typed TARGET-subject
        # sources with non-root paths via discover_subpages. urlparse
        # gives us the path component reliably; root is "" or "/".
        elif (src.source_type.value == "site"
              and subj == "target"
              and _is_subpath(url)):
            expanded += 1

    stats.sources_total = len(bundle.sources)
    stats.by_tier = by_tier
    stats.by_subject = by_subject
    stats.by_source_type = by_source_type
    stats.expanded_subpages = expanded
    stats.chrome_fallbacks = chrome
    stats.expert_quote_count = expert_quote_count
    return stats


def _emit(on_event: EventCallback | None, event: dict) -> dict:
    """Side-effecting event sink. A sink failure must never break the cascade."""
    if on_event is not None:
        try:
            on_event(event)
        except Exception:
            pass
    return event


def _ground_dept(model, bundle: SharedBundle):
    fields = _DEPT_FIELDS[type(model)]
    dropped: list[str] = []
    updates: dict = {}
    for field in fields:
        kept, drp = grounding.filter_claims(getattr(model, field), bundle)
        updates[field] = kept
        dropped.extend(drp)
    return model.model_copy(update=updates), dropped


def _citations_of(*claim_lists: list[Claim]) -> list[Citation]:
    cites: list[Citation] = []
    for claims in claim_lists:
        if claims and claims[0].citations:
            cites.append(claims[0].citations[0])
    return cites


def _urls_of(claims: list[Claim]) -> list[str]:
    return [c.url for cl in claims for c in cl.citations]


def _executive_summary(ab: AccountBrief, ms: MarketSignal, rp: RiskProfile,
                        synergies: list[SynergySignal]) -> str:
    parts = [
        f"{ab.target}: {len(ab.buying_signals)} buying / "
        f"{len(ab.hiring_signals)} hiring signals; "
        f"{len(ms.pricing_trend)} pricing moves; "
        f"{len(rp.all_claims())} risk signals."
    ]
    if synergies:
        parts.append("Cross-dept: " + synergies[0].text)
    return " ".join(parts)


# V7.28 — When the strategy LLM's citation snippets are paraphrased rather
# than verbatim, the cite-level grounding pass prunes them away and the play
# ends up with `citations: []`. That breaks the "every play has an evidence
# chain" promise. Fallback: pull the strongest citation from each owner-dept
# whose claims fed into the strategist, so plays always carry some traceable
# evidence trail.
_OWNER_TO_STATE_KEY = {
    "gtm":       "account_brief",
    "finance":   "market_signal",
    "security":  "risk_profile",
    "marketing": "marketing_signal",
}


def _fallback_play_citations(play, state: "CascadeState") -> list[Citation]:
    """Pull one citation per owner dept from the most-populated claim field."""
    out: list[Citation] = []
    seen: set[str] = set()
    for owner in (play.owners or []):
        key = _OWNER_TO_STATE_KEY.get(owner)
        if key is None:
            continue
        dept = state.get(key)
        if dept is None:
            continue
        # walk dept fields, find first non-empty claim list, take first cite
        for field_name in type(dept).model_fields:
            claims = getattr(dept, field_name, None)
            if not isinstance(claims, list) or not claims:
                continue
            first = claims[0]
            cites = getattr(first, "citations", None)
            if not cites:
                continue
            cite = cites[0]
            if cite.url in seen:
                continue
            seen.add(cite.url)
            out.append(cite)
            break
    return out


def _business_context_block(profile: BusinessProfile | None) -> str:
    """Render a BusinessProfile as compact prompt context for self-mode."""
    if not profile:
        return ""
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


def build_graph(
    gtm_llm: LLMFn | None = None,
    finance_llm: LLMFn | None = None,
    security_llm: LLMFn | None = None,
    strategy_llm: LLMFn | None = None,
    marketing_llm: LLMFn | None = None,
    contradictions_llm: LLMFn | None = None,
    porter_llm: LLMFn | None = None,
    swot_llm: LLMFn | None = None,
    pestle_llm: LLMFn | None = None,
    profile_llm: LLMFn | None = None,            # V7.28
    sector_llm: LLMFn | None = None,             # V7.29
    expert_quotes_llm: LLMFn | None = None,      # V7.34
    cross_pollinate_llm: LLMFn | None = None,    # V7.35
    on_event: EventCallback | None = None,
    mode: CascadeMode = CascadeMode.TARGET,
    business_profile: BusinessProfile | None = None,
):
    """Compile the StateGraph. LLMs are closure-bound so state stays serializable.

    `mode` and `business_profile` are also closure-bound — they shape the
    prompts the depts and the strategy agent use (self-mode advises the
    founder, target-mode analyses someone else).
    """
    from langgraph.graph import END, START, StateGraph

    def pii_node(state: CascadeState) -> dict:
        start = _emit(on_event, {"t": _now_iso(), "phase": "pii", "status": "start"})
        clean, count = pii.redact_bundle(state["bundle"])
        done = _emit(on_event, {
            "t": _now_iso(), "phase": "pii", "status": "done", "redactions": count,
        })
        return {"clean": clean, "pii_count": count, "events": [start, done]}

    def leak_node(state: CascadeState) -> dict:
        start = _emit(on_event, {"t": _now_iso(), "phase": "leak", "status": "start"})
        clean, flags = leak.filter_bundle(state["clean"])
        done = _emit(on_event, {
            "t": _now_iso(), "phase": "leak", "status": "done", "flags": flags,
        })
        return {"clean": clean, "leak_flags": flags, "events": [start, done]}

    business_block = _business_context_block(business_profile)

    def _dept_node(dept: str, analyze, llm: LLMFn | None, out_key: str):
        def _node(state: CascadeState) -> dict:
            start = _emit(on_event, {
                "t": _now_iso(), "phase": "dept", "dept": dept, "status": "start",
            })
            result = analyze(state["clean"], llm=llm)
            done = _emit(on_event, {
                "t": _now_iso(), "phase": "dept", "dept": dept, "status": "done",
                "claims": len(result.all_claims()),
            })
            return {out_key: result, "events": [start, done]}

        return _node

    def _marketing_node(state: CascadeState) -> dict:
        start = _emit(on_event, {
            "t": _now_iso(), "phase": "dept", "dept": "marketing", "status": "start",
        })
        result = marketing_agent.analyze(
            state["clean"],
            llm=marketing_llm,
            mode=mode,
            business_context=business_block,
        )
        done = _emit(on_event, {
            "t": _now_iso(), "phase": "dept", "dept": "marketing", "status": "done",
            "claims": len(result.all_claims()),
        })
        return {"marketing_signal": result, "events": [start, done]}

    def grounding_node(state: CascadeState) -> dict:
        start = _emit(on_event, {"t": _now_iso(), "phase": "grounding", "status": "start"})
        clean = state["clean"]
        ab, da = _ground_dept(state["account_brief"], clean)
        ms, dm = _ground_dept(state["market_signal"], clean)
        rp, ds = _ground_dept(state["risk_profile"], clean)
        updates = {
            "account_brief": ab,
            "market_signal": ms,
            "risk_profile": rp,
        }
        dropped = [*da, *dm, *ds]
        # marketing only present when its node ran (always, in V7+)
        if state.get("marketing_signal") is not None:
            mk, dmk = _ground_dept(state["marketing_signal"], clean)
            updates["marketing_signal"] = mk
            dropped.extend(dmk)
        done = _emit(on_event, {
            "t": _now_iso(), "phase": "grounding", "status": "done",
            "dropped": len(dropped),
        })
        return {**updates, "dropped": dropped, "events": [start, done]}

    def _templated_cross_pollinate(state: CascadeState) -> tuple[list[HandoffMessage], list[SynergySignal]]:
        """Deterministic V7.0 cross-pollinate. Now the fallback when the
        V7.35 LLM path returns empty (or fails). Identical behaviour to
        the pre-V7.35 implementation — kept so the cascade always has at
        least the boilerplate cross-talk."""
        ab = state.get("account_brief")
        ms = state.get("market_signal")
        rp = state.get("risk_profile")
        hs: list[HandoffMessage] = []
        ss: list[SynergySignal] = []
        if ms and ms.pricing_trend:
            hs.append(HandoffMessage(
                from_dept="finance", to_dept="gtm",
                message="Pricing change detected — adjust outreach timing/messaging.",
                refs=_urls_of(ms.pricing_trend),
            ))
        if rp and rp.reputational_signals:
            hs.append(HandoffMessage(
                from_dept="security", to_dept="gtm",
                message="Reputational signal — frame responsibly, do not weaponize.",
                refs=_urls_of(rp.reputational_signals),
            ))
        if ab and ab.hiring_signals:
            hs.append(HandoffMessage(
                from_dept="gtm", to_dept="security",
                message="Hiring expansion — new attack surface / vendors to monitor.",
                refs=_urls_of(ab.hiring_signals),
            ))
        if ms and rp and ms.pricing_trend and rp.reputational_signals:
            ss.append(SynergySignal(
                text=("Pricing increase coincides with support/reputation complaints "
                      "— churn risk; time GTM outreach around retention, not upsell."),
                contributing_depts=["finance", "security"],
                citations=_citations_of(ms.pricing_trend, rp.reputational_signals),
            ))
        if ab and ms and ab.hiring_signals and (ms.expansion_contraction or ab.buying_signals):
            ss.append(SynergySignal(
                text=("Hiring plus funding/expansion signals a growth account — "
                      "prioritize and resource the outreach."),
                contributing_depts=["gtm", "finance"],
                citations=_citations_of(
                    ab.hiring_signals, ms.expansion_contraction or ab.buying_signals
                ),
            ))
        return hs, ss

    def cross_node(state: CascadeState) -> dict:
        """V7.35 — LLM-driven cross-pollination w/ templated fallback.

        Reads all 4 dept signals + business profile + sector signal,
        calls the cross_pollinate_llm agent to produce per-company
        handoffs + synergies. If the LLM returns 0 of EACH (parse fail,
        empty response, etc.), falls back to the deterministic
        templated cross_pollinate so the cascade never ends up with
        an empty cross-talk layer.

        Emits one start + one done event for the dashboard SSE stream,
        plus per-handoff and per-synergy events (same as the V7.0
        templated version) so the cytoscape arc animation still fires
        in the same sequence.
        """
        start = _emit(on_event, {
            "t": _now_iso(), "phase": "cross_pollinate", "status": "start",
        })

        ab = state.get("account_brief")
        ms = state.get("market_signal")
        mk = state.get("marketing_signal")
        rp = state.get("risk_profile")
        profile = state.get("business_profile") or business_profile
        sector = state.get("sector")
        sector_signal = state.get("sector_signal")

        handoffs: list[HandoffMessage] = []
        synergies: list[SynergySignal] = []
        source = "fallback"
        try:
            llm_handoffs, llm_synergies = cross_pollinate_llm_agent.analyze(
                account_brief=ab,
                market_signal=ms,
                marketing_signal=mk,
                risk_profile=rp,
                business_profile=profile,
                sector=sector,
                sector_signal=sector_signal,
                target=state["bundle"].target,
                llm=cross_pollinate_llm,
            )
            if llm_handoffs or llm_synergies:
                handoffs, synergies = llm_handoffs, llm_synergies
                source = "llm"
        except Exception as exc:
            _emit(on_event, {
                "t": _now_iso(), "phase": "cross_pollinate", "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            # fall through to templated fallback

        if not handoffs and not synergies:
            handoffs, synergies = _templated_cross_pollinate(state)
            source = "fallback"

        # Emit per-edge events so the cytoscape arc animation still drives
        # the same way it always did (frontend listens for these).
        evs = [start]
        for h in handoffs:
            evs.append(_emit(on_event, {
                "t": _now_iso(), "phase": "handoff",
                "from": h.from_dept, "to": h.to_dept, "message": h.message,
            }))
        for s in synergies:
            evs.append(_emit(on_event, {
                "t": _now_iso(), "phase": "synergy",
                "depts": s.contributing_depts, "text": s.text,
            }))
        evs.append(_emit(on_event, {
            "t": _now_iso(), "phase": "cross_pollinate", "status": "done",
            "source": source,
            "handoffs": len(handoffs), "synergies": len(synergies),
        }))
        return {"synergies": synergies, "handoffs": handoffs, "events": evs}

    def profile_extract_node(state: CascadeState) -> dict:
        """V7.28 — extract a BusinessProfile from the bundle in target-mode so
        the dashboard's profile section + the industry chip can render, and so
        the strategy prompt sees industry/stage context. Skipped in self-mode
        (the founder already provided one via the onboarding form)."""
        if mode == CascadeMode.SELF:
            # pass through the closure-bound profile (set by self-mode flow)
            if business_profile is not None:
                return {"business_profile": business_profile}
            return {}
        start = _emit(on_event, {"t": _now_iso(), "phase": "profile", "status": "start"})
        try:
            profile = profile_agent.analyze(
                state.get("clean", state["bundle"]),
                llm=profile_llm,
            )
        except Exception as exc:
            err = _emit(on_event, {
                "t": _now_iso(), "phase": "profile", "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            # minimal fallback so downstream can still render the target name
            fallback = BusinessProfile(name=state["bundle"].target, url="")
            return {"business_profile": fallback, "events": [start, err]}
        done = _emit(on_event, {
            "t": _now_iso(), "phase": "profile", "status": "done",
            "industry": profile.industry,
            "stage": profile.stage.value if hasattr(profile.stage, "value") else str(profile.stage),
            "competitors": len(profile.competitor_names or []),
        })
        return {"business_profile": profile, "events": [start, done]}

    def sector_node(state: CascadeState) -> dict:
        """V7.29 — sector-conditional sub-pipeline. Reads profile.industry
        (extracted upstream in profile_extract or supplied in self-mode),
        routes to the matching sector agent (pharma / saas / energy / generic),
        and returns a typed SectorSignal. One LLM call. Failures fall back
        to an empty signal of the right type — never breaks cascade."""
        profile = state.get("business_profile") or business_profile
        start = _emit(on_event, {"t": _now_iso(), "phase": "sector", "status": "start"})
        try:
            sector, signal = sector_agent.analyze(
                bundle=state.get("clean", state["bundle"]),
                profile=profile,
                llm=sector_llm,
            )
        except Exception as exc:
            err = _emit(on_event, {
                "t": _now_iso(), "phase": "sector", "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            return {
                "sector": Sector.GENERIC,
                "sector_signal": GenericSignal(),
                "events": [start, err],
            }
        # one-line summary of what the sector branch produced
        if isinstance(signal, PharmaSignal):
            counts = f"pipeline={len(signal.pipeline)} subs={len(signal.submissions)} partners={len(signal.partners)}"
        elif isinstance(signal, SaasSignal):
            counts = f"tiers={len(signal.tiers)} plg={len(signal.plg_metrics)} logos={len(signal.reference_logos)}"
        elif isinstance(signal, EnergySignal):
            counts = f"sites={len(signal.sites)} certs={len(signal.certifications)} grid={len(signal.grid_deals)}"
        else:
            counts = f"moats={len(signal.moats)} cadence={len(signal.cadence)}"
        done = _emit(on_event, {
            "t": _now_iso(), "phase": "sector", "status": "done",
            "sector": sector.value, "counts": counts,
        })
        return {"sector": sector, "sector_signal": signal, "events": [start, done]}

    def expert_quotes_node(state: CascadeState) -> dict:
        """V7.34 — extract named-individual verbatim quotes from the bundle.

        Runs serially between profile_extract and sector_pass so the
        post-grounding 5-way reasoning fan-out stays equal-depth (a
        6-way fan-out from sector_pass would risk the same Vertex
        degradation pattern V7.29-pt3 fixed for sector_pass). One LLM
        call; failures degrade to an empty list and never break cascade.
        """
        start = _emit(on_event, {
            "t": _now_iso(), "phase": "expert_quotes", "status": "start",
        })
        try:
            quotes = expert_quotes_agent.analyze(
                bundle=state.get("clean", state["bundle"]),
                llm=expert_quotes_llm,
            )
        except Exception as exc:
            err = _emit(on_event, {
                "t": _now_iso(), "phase": "expert_quotes", "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            return {"expert_quotes": [], "events": [start, err]}
        done = _emit(on_event, {
            "t": _now_iso(), "phase": "expert_quotes", "status": "done",
            "count": len(quotes),
        })
        return {"expert_quotes": quotes, "events": [start, done]}

    def strategy_node(state: CascadeState) -> dict:
        """Synthesize all dept outputs + synergies + handoffs into a
        StrategicPlan via an LLM. The 'answer' layer.

        Failures here are caught so a malformed plan doesn't lose the rest
        of the cascade: the assemble node still builds a CascadeBrief, the
        plan just stays None and the dashboard hides its hero section.
        """
        start = _emit(on_event, {"t": _now_iso(), "phase": "strategy", "status": "start"})
        try:
            # V7.28 — prefer the (possibly LLM-extracted) profile from state
            # over the closure-bound founder profile, so target-mode strategy
            # gets the inferred industry context too.
            profile_for_strategy = state.get("business_profile") or business_profile
            plan = strategy_agent.analyze(
                target=state["bundle"].target,
                account_brief=state["account_brief"],
                market_signal=state["market_signal"],
                risk_profile=state["risk_profile"],
                synergies=state.get("synergies", []),
                handoffs=state.get("handoffs", []),
                llm=strategy_llm,
                mode=mode,
                business_profile=profile_for_strategy,
                marketing_signal=state.get("marketing_signal"),
            )
            # V7.22-pt3 + V7.28 — apply cite-level grounding to strategy plays.
            # The strategy LLM tends to paraphrase rather than copy snippets
            # verbatim, so its own citations slip past the guard. Prune them
            # the same way dept claims are pruned. V7.28: when pruning leaves
            # a play with `citations: []`, fall back to one citation per
            # owner-dept (top claim, top cite) so every play always carries
            # SOME traceable evidence trail back to the bundle.
            if plan and plan.recommended_plays:
                haystacks = [grounding._norm(t) for t in state["bundle"].texts()]
                cleaned_plays = []
                for play in plan.recommended_plays:
                    good = [c for c in play.citations if grounding._cite_is_grounded(c, haystacks)]
                    if not good:
                        good = _fallback_play_citations(play, state)
                    if good != list(play.citations):
                        cleaned_plays.append(play.model_copy(update={"citations": good}))
                    else:
                        cleaned_plays.append(play)
                plan = plan.model_copy(update={"recommended_plays": cleaned_plays})
            done = _emit(on_event, {
                "t": _now_iso(), "phase": "strategy", "status": "done",
                "headline": plan.headline,
                "plays": len(plan.recommended_plays),
                "icp_fit": plan.icp_fit.value,
                "urgency": plan.urgency,
            })
            return {"strategic_plan": plan, "events": [start, done]}
        except Exception as exc:
            err = _emit(on_event, {
                "t": _now_iso(), "phase": "strategy", "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            return {"events": [start, err]}

    def porter_node(state: CascadeState) -> dict:
        """V7.24 — Porter's Five Forces against the clean bundle."""
        start = _emit(on_event, {
            "t": _now_iso(), "phase": "porter", "status": "start",
        })
        try:
            five = porter_agent.analyze(
                target=state["bundle"].target,
                bundle=state.get("clean", state["bundle"]),
                llm=porter_llm,
            )
        except Exception as exc:
            err = _emit(on_event, {
                "t": _now_iso(), "phase": "porter", "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            return {"five_forces": FiveForces(), "events": [start, err]}
        done = _emit(on_event, {
            "t": _now_iso(), "phase": "porter", "status": "done",
            "rivalry": five.rivalry.intensity,
            "new_entrants": five.new_entrants.intensity,
            "supplier_power": five.supplier_power.intensity,
            "buyer_power": five.buyer_power.intensity,
            "substitutes": five.substitutes.intensity,
        })
        return {"five_forces": five, "events": [start, done]}

    def pestle_node(state: CascadeState) -> dict:
        """V7.26 — PESTLE macro-environment analysis against the clean bundle."""
        start = _emit(on_event, {
            "t": _now_iso(), "phase": "pestle", "status": "start",
        })
        try:
            p = pestle_agent.analyze(
                target=state["bundle"].target,
                bundle=state.get("clean", state["bundle"]),
                llm=pestle_llm,
            )
        except Exception as exc:
            err = _emit(on_event, {
                "t": _now_iso(), "phase": "pestle", "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            return {"pestle": Pestle(), "events": [start, err]}
        done = _emit(on_event, {
            "t": _now_iso(), "phase": "pestle", "status": "done",
            "political": p.political.pressure,
            "economic": p.economic.pressure,
            "social": p.social.pressure,
            "technological": p.technological.pressure,
            "legal": p.legal.pressure,
            "environmental": p.environmental.pressure,
        })
        return {"pestle": p, "events": [start, done]}

    def swot_node(state: CascadeState) -> dict:
        """V7.24 — SWOT against the clean bundle."""
        start = _emit(on_event, {
            "t": _now_iso(), "phase": "swot", "status": "start",
        })
        try:
            sw = swot_agent.analyze(
                target=state["bundle"].target,
                bundle=state.get("clean", state["bundle"]),
                llm=swot_llm,
            )
        except Exception as exc:
            err = _emit(on_event, {
                "t": _now_iso(), "phase": "swot", "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            return {"swot": Swot(), "events": [start, err]}
        done = _emit(on_event, {
            "t": _now_iso(), "phase": "swot", "status": "done",
            "s": len(sw.strengths), "w": len(sw.weaknesses),
            "o": len(sw.opportunities), "t_": len(sw.threats),
        })
        return {"swot": sw, "events": [start, done]}

    def contradictions_node(state: CascadeState) -> dict:
        """V7.23 — surface mutually-inconsistent claim pairs across depts.

        Runs in parallel with strategy after cross_pollinate. Both consume
        the grounded dept outputs; both feed into assemble. A failure here
        leaves contradictions empty (it's a 'nice to have' layer, not a
        gate) so the rest of the brief still ships.
        """
        start = _emit(on_event, {
            "t": _now_iso(), "phase": "contradictions", "status": "start",
        })
        try:
            cs = contradictions_agent.analyze(
                target=state["bundle"].target,
                account_brief=state.get("account_brief"),
                market_signal=state.get("market_signal"),
                risk_profile=state.get("risk_profile"),
                marketing_signal=state.get("marketing_signal"),
                llm=contradictions_llm,
            )
        except Exception as exc:
            err = _emit(on_event, {
                "t": _now_iso(), "phase": "contradictions", "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            return {"contradictions": [], "events": [start, err]}
        done = _emit(on_event, {
            "t": _now_iso(), "phase": "contradictions", "status": "done",
            "found": len(cs),
        })
        return {"contradictions": cs, "events": [start, done]}

    def assemble_node(state: CascadeState) -> dict:
        ab = state["account_brief"]
        ms = state["market_signal"]
        rp = state["risk_profile"]
        mk = state.get("marketing_signal")
        dropped = state.get("dropped", [])
        report = GuardrailReport(
            pii_redactions=state.get("pii_count", 0),
            leak_flags=state.get("leak_flags", []),
            ungrounded_dropped=dropped,
            passed=(len(dropped) == 0),
        )
        synergies = state.get("synergies", [])
        plan = state.get("strategic_plan")
        # If a strategic plan was produced, prefer its headline as the exec
        # summary — it's an LLM-written narrative, not a templated counts string.
        exec_summary = (
            f"{plan.headline} — {plan.urgency}." if plan and plan.headline
            else _executive_summary(ab, ms, rp, synergies)
        )
        # V7.28 — surface the (possibly LLM-extracted) target-mode profile
        # in the brief so the dashboard can render industry/stage/competitors.
        # V7.29 — route the sector_signal into the typed CascadeBrief slot so
        # the frontend can render the correct sector-specific panel.
        sector_kwargs: dict = {}
        sector = state.get("sector")
        signal = state.get("sector_signal")
        if sector is not None and signal is not None:
            sector_kwargs["sector"] = sector
            if isinstance(signal, PharmaSignal):
                sector_kwargs["pharma_signal"] = signal
            elif isinstance(signal, SaasSignal):
                sector_kwargs["saas_signal"] = signal
            elif isinstance(signal, EnergySignal):
                sector_kwargs["energy_signal"] = signal
            elif isinstance(signal, GenericSignal):
                sector_kwargs["generic_signal"] = signal

        # V7.37 — per-cascade bundle quality snapshot. Uses the post-
        # grounding clean bundle (what the depts actually read).
        expert_quotes_list = state.get("expert_quotes", [])
        bundle_stats = _compute_bundle_stats(
            state.get("clean", state.get("bundle")),
            expert_quote_count=len(expert_quotes_list),
        )
        brief = CascadeBrief(
            target=state["bundle"].target,
            mode=mode,
            business_profile=state.get("business_profile") or business_profile,
            account_brief=ab,
            market_signal=ms,
            marketing_signal=mk,
            risk_profile=rp,
            synergy_signals=synergies,
            handoffs=state.get("handoffs", []),
            contradictions=state.get("contradictions", []),
            five_forces=state.get("five_forces"),
            swot=state.get("swot"),
            pestle=state.get("pestle"),
            guardrail_report=report,
            executive_summary=exec_summary,
            strategic_plan=plan,
            expert_quotes=expert_quotes_list,                # V7.34
            bundle_stats=bundle_stats,                       # V7.37
            **sector_kwargs,
        )
        total_claims = (
            len(brief.account_brief.all_claims())
            + len(brief.market_signal.all_claims())
            + len(brief.risk_profile.all_claims())
            + (len(brief.marketing_signal.all_claims()) if brief.marketing_signal else 0)
        )
        done = _emit(on_event, {
            "t": _now_iso(), "phase": "assemble", "status": "done",
            "passed": report.passed, "claims": total_claims,
            "mode": mode.value,
        })
        return {"brief": brief, "events": [done]}

    g = StateGraph(CascadeState)
    g.add_node("pii_redact", pii_node)
    g.add_node("leak_filter", leak_node)
    g.add_node("gtm", _dept_node("gtm", gtm_agent.analyze, gtm_llm, "account_brief"))
    g.add_node(
        "finance",
        _dept_node("finance", finance_agent.analyze, finance_llm, "market_signal"),
    )
    g.add_node("marketing", _marketing_node)
    g.add_node(
        "security",
        _dept_node("security", security_agent.analyze, security_llm, "risk_profile"),
    )
    g.add_node("grounding", grounding_node)
    g.add_node("cross_pollinate", cross_node)
    g.add_node("profile_extract", profile_extract_node)     # V7.28 — feeds strategy
    # V7.34 — node name MUST differ from the 'expert_quotes' state key
    # (LangGraph rejects collisions); _pass suffix matches sector_pass /
    # contradictions_pass / porter_pass / swot_pass / pestle_pass.
    g.add_node("expert_quotes_pass", expert_quotes_node)
    g.add_node("sector_pass", sector_node)                  # V7.29 — sector sub-pipeline
    g.add_node("strategy", strategy_node)
    g.add_node("contradictions_pass", contradictions_node)  # node name must differ from state key
    g.add_node("porter_pass", porter_node)                  # V7.24
    g.add_node("swot_pass", swot_node)                      # V7.24
    g.add_node("pestle_pass", pestle_node)                  # V7.26
    g.add_node("assemble", assemble_node)

    g.add_edge(START, "pii_redact")
    g.add_edge("pii_redact", "leak_filter")
    # parallel fan-out: four dept agents on the shared clean bundle
    g.add_edge("leak_filter", "gtm")
    g.add_edge("leak_filter", "finance")
    g.add_edge("leak_filter", "marketing")
    g.add_edge("leak_filter", "security")
    # join: grounding runs once all four depts complete
    g.add_edge("gtm", "grounding")
    g.add_edge("finance", "grounding")
    g.add_edge("marketing", "grounding")
    g.add_edge("security", "grounding")
    g.add_edge("grounding", "cross_pollinate")
    # parallel branch after cross_pollinate:
    #   profile_extract → strategy  (V7.28 — profile feeds the strategy prompt)
    #   contradictions_pass         — opposing-source claim pairs (V7.23)
    #   porter_pass                 — Porter's 5 Forces analysis (V7.24)
    #   swot_pass                   — SWOT 2x2 (V7.24)
    #   pestle_pass                 — PESTLE 2x3 (V7.26)
    # V7.29-pt3 — two serial gates (profile_extract, sector_pass) then 5-way
    # parallel fan-out to the universal reasoning agents. Earlier topology
    # had sector_pass parallel with strategy + 4 frameworks (6-way fan-out),
    # but Vertex degrades responses when 6 LLM calls fire simultaneously —
    # sector returned empty lists silently. Serialising sector_pass right
    # after profile_extract costs ~30s of wall clock but guarantees the
    # sector signal actually populates. The 5 remaining reasoning agents
    # still fan parallel from sector_pass, equal-depth, so the LangGraph
    # fan-in barrier into assemble stays clean (no double-fire).
    g.add_edge("cross_pollinate", "profile_extract")
    # V7.34 — expert_quotes_pass runs serially between profile_extract and
    # sector_pass. Keeps the post-sector 5-way fan-in equal-depth.
    g.add_edge("profile_extract", "expert_quotes_pass")
    g.add_edge("expert_quotes_pass", "sector_pass")
    g.add_edge("sector_pass", "strategy")
    g.add_edge("sector_pass", "contradictions_pass")
    g.add_edge("sector_pass", "porter_pass")
    g.add_edge("sector_pass", "swot_pass")
    g.add_edge("sector_pass", "pestle_pass")
    # five reasoning branches join into assemble
    g.add_edge("strategy", "assemble")
    g.add_edge("contradictions_pass", "assemble")
    g.add_edge("porter_pass", "assemble")
    g.add_edge("swot_pass", "assemble")
    g.add_edge("pestle_pass", "assemble")
    g.add_edge("assemble", END)

    return g.compile()


def run(
    bundle: SharedBundle,
    gtm_llm: LLMFn | None = None,
    finance_llm: LLMFn | None = None,
    security_llm: LLMFn | None = None,
    strategy_llm: LLMFn | None = None,
    marketing_llm: LLMFn | None = None,
    profile_llm: LLMFn | None = None,            # V7.28
    sector_llm: LLMFn | None = None,             # V7.29
    expert_quotes_llm: LLMFn | None = None,      # V7.34
    cross_pollinate_llm: LLMFn | None = None,    # V7.35
    event_path: Path | None = None,
    mode: CascadeMode = CascadeMode.TARGET,
    business_profile: BusinessProfile | None = None,
) -> CascadeBrief:
    """Run the cascade graph end-to-end.

    If `event_path` is provided, each node emits a JSON event to that file
    (one JSON object per line) as it fires — used by the dashboard's V3.2
    replay mode to animate the cascade unfolding.
    """
    handle = None
    on_event: EventCallback | None = None
    if event_path is not None:
        event_path = Path(event_path)
        event_path.parent.mkdir(parents=True, exist_ok=True)
        handle = event_path.open("w")

        def _write(ev: dict) -> None:
            # only `dict` w/ JSON-safe values is emitted; events come from this
            # module so we control the shape — json.dumps is safe here.
            handle.write(json.dumps(ev) + "\n")
            handle.flush()

        on_event = _write

    try:
        graph = build_graph(
            gtm_llm=gtm_llm,
            finance_llm=finance_llm,
            security_llm=security_llm,
            strategy_llm=strategy_llm,
            marketing_llm=marketing_llm,
            profile_llm=profile_llm,                # V7.28
            sector_llm=sector_llm,                  # V7.29
            expert_quotes_llm=expert_quotes_llm,    # V7.34
            cross_pollinate_llm=cross_pollinate_llm,  # V7.35
            on_event=on_event,
            mode=mode,
            business_profile=business_profile,
        )
        final = graph.invoke({"bundle": bundle, "events": []})
        return final["brief"]
    finally:
        if handle is not None:
            handle.close()
