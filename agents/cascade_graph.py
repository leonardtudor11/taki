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

from agents import finance as finance_agent
from agents import gtm as gtm_agent
from agents import contradictions as contradictions_agent
from agents import marketing as marketing_agent
from agents import pestle as pestle_agent
from agents import porter as porter_agent
from agents import security as security_agent
from agents import strategy as strategy_agent
from agents import swot as swot_agent
from agents.schemas import (
    AccountBrief,
    BusinessProfile,
    CascadeBrief,
    CascadeMode,
    Citation,
    Claim,
    Contradiction,
    FiveForces,
    GuardrailReport,
    HandoffMessage,
    MarketSignal,
    MarketingSignal,
    Pestle,
    RiskProfile,
    SharedBundle,
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    def cross_node(state: CascadeState) -> dict:
        ab, ms, rp = state["account_brief"], state["market_signal"], state["risk_profile"]
        synergies: list[SynergySignal] = []
        handoffs: list[HandoffMessage] = []
        evs: list[dict] = []

        if ms.pricing_trend:
            h = HandoffMessage(
                from_dept="finance",
                to_dept="gtm",
                message="Pricing change detected — adjust outreach timing/messaging.",
                refs=_urls_of(ms.pricing_trend),
            )
            handoffs.append(h)
            evs.append(_emit(on_event, {
                "t": _now_iso(), "phase": "handoff",
                "from": h.from_dept, "to": h.to_dept, "message": h.message,
            }))
        if rp.reputational_signals:
            h = HandoffMessage(
                from_dept="security",
                to_dept="gtm",
                message="Reputational signal — frame responsibly, do not weaponize.",
                refs=_urls_of(rp.reputational_signals),
            )
            handoffs.append(h)
            evs.append(_emit(on_event, {
                "t": _now_iso(), "phase": "handoff",
                "from": h.from_dept, "to": h.to_dept, "message": h.message,
            }))
        if ab.hiring_signals:
            h = HandoffMessage(
                from_dept="gtm",
                to_dept="security",
                message="Hiring expansion — new attack surface / vendors to monitor.",
                refs=_urls_of(ab.hiring_signals),
            )
            handoffs.append(h)
            evs.append(_emit(on_event, {
                "t": _now_iso(), "phase": "handoff",
                "from": h.from_dept, "to": h.to_dept, "message": h.message,
            }))

        if ms.pricing_trend and rp.reputational_signals:
            s = SynergySignal(
                text=(
                    "Pricing increase coincides with support/reputation complaints "
                    "— churn risk; time GTM outreach around retention, not upsell."
                ),
                contributing_depts=["finance", "security"],
                citations=_citations_of(ms.pricing_trend, rp.reputational_signals),
            )
            synergies.append(s)
            evs.append(_emit(on_event, {
                "t": _now_iso(), "phase": "synergy",
                "depts": s.contributing_depts, "text": s.text,
            }))
        if ab.hiring_signals and (ms.expansion_contraction or ab.buying_signals):
            s = SynergySignal(
                text=(
                    "Hiring plus funding/expansion signals a growth account — "
                    "prioritize and resource the outreach."
                ),
                contributing_depts=["gtm", "finance"],
                citations=_citations_of(
                    ab.hiring_signals, ms.expansion_contraction or ab.buying_signals
                ),
            )
            synergies.append(s)
            evs.append(_emit(on_event, {
                "t": _now_iso(), "phase": "synergy",
                "depts": s.contributing_depts, "text": s.text,
            }))

        return {"synergies": synergies, "handoffs": handoffs, "events": evs}

    def strategy_node(state: CascadeState) -> dict:
        """Synthesize all dept outputs + synergies + handoffs into a
        StrategicPlan via an LLM. The 'answer' layer.

        Failures here are caught so a malformed plan doesn't lose the rest
        of the cascade: the assemble node still builds a CascadeBrief, the
        plan just stays None and the dashboard hides its hero section.
        """
        start = _emit(on_event, {"t": _now_iso(), "phase": "strategy", "status": "start"})
        try:
            plan = strategy_agent.analyze(
                target=state["bundle"].target,
                account_brief=state["account_brief"],
                market_signal=state["market_signal"],
                risk_profile=state["risk_profile"],
                synergies=state.get("synergies", []),
                handoffs=state.get("handoffs", []),
                llm=strategy_llm,
                mode=mode,
                business_profile=business_profile,
                marketing_signal=state.get("marketing_signal"),
            )
            # V7.22-pt3 — apply cite-level grounding to strategy plays.
            # The strategy LLM tends to paraphrase rather than copy snippets
            # verbatim, so its citations slip past the guard. Prune them
            # the same way dept claims are pruned. Plays w/ 0 verified
            # cites are kept (the play conclusion may still be valid as
            # a synthesis of verified dept claims) but render w/o evidence.
            if plan and plan.recommended_plays:
                haystacks = [grounding._norm(t) for t in state["bundle"].texts()]
                cleaned_plays = []
                for play in plan.recommended_plays:
                    good = [c for c in play.citations if grounding._cite_is_grounded(c, haystacks)]
                    if len(good) != len(play.citations):
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
        brief = CascadeBrief(
            target=state["bundle"].target,
            mode=mode,
            business_profile=business_profile,
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
    #   strategy            — synthesize the plan
    #   contradictions_pass — opposing-source claim pairs (V7.23)
    #   porter_pass         — Porter's 5 Forces analysis (V7.24)
    #   swot_pass           — SWOT 2x2 (V7.24)
    g.add_edge("cross_pollinate", "strategy")
    g.add_edge("cross_pollinate", "contradictions_pass")
    g.add_edge("cross_pollinate", "porter_pass")
    g.add_edge("cross_pollinate", "swot_pass")
    g.add_edge("cross_pollinate", "pestle_pass")  # V7.26
    # all five join into assemble
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
            on_event=on_event,
            mode=mode,
            business_profile=business_profile,
        )
        final = graph.invoke({"bundle": bundle, "events": []})
        return final["brief"]
    finally:
        if handle is not None:
            handle.close()
