"""V6 — strategy department + StateGraph integration."""

import json

from agents import cascade_graph, strategy
from agents.schemas import CascadeBrief, FitTier, StrategicPlan
from fixtures.fake_llm import (
    fake_finance_llm,
    fake_gtm_llm,
    fake_marketing_llm,
    fake_security_llm,
    fake_strategy_llm,
)
from fixtures.sample import sample_bundle

_FAKES = dict(
    gtm_llm=fake_gtm_llm,
    finance_llm=fake_finance_llm,
    marketing_llm=fake_marketing_llm,
    security_llm=fake_security_llm,
    strategy_llm=fake_strategy_llm,
)


# ─── unit ─────────────────────────────────────────────────────────────────

def test_strategy_agent_returns_strategic_plan():
    # build dept outputs first
    ab = __import__("agents.gtm", fromlist=["analyze"]).analyze(sample_bundle(), llm=fake_gtm_llm)
    ms = __import__("agents.finance", fromlist=["analyze"]).analyze(sample_bundle(), llm=fake_finance_llm)
    rp = __import__("agents.security", fromlist=["analyze"]).analyze(sample_bundle(), llm=fake_security_llm)

    plan = strategy.analyze(
        target="Northwind Analytics",
        account_brief=ab,
        market_signal=ms,
        risk_profile=rp,
        synergies=[],
        handoffs=[],
        llm=fake_strategy_llm,
    )
    assert isinstance(plan, StrategicPlan)
    assert plan.target == "Northwind Analytics"
    assert plan.headline
    assert plan.narrative
    assert plan.icp_fit in (FitTier.HIGH, FitTier.MEDIUM, FitTier.LOW)
    assert plan.deal_size_estimate
    assert plan.urgency
    assert plan.recommended_plays, "expected at least one prioritized play"
    assert plan.open_questions, "expected open questions to fill"


def test_strategy_plays_are_priority_ordered():
    plan = strategy.analyze(
        target="X",
        account_brief=__import__("agents.gtm", fromlist=["analyze"]).analyze(sample_bundle(), llm=fake_gtm_llm),
        market_signal=__import__("agents.finance", fromlist=["analyze"]).analyze(sample_bundle(), llm=fake_finance_llm),
        risk_profile=__import__("agents.security", fromlist=["analyze"]).analyze(sample_bundle(), llm=fake_security_llm),
        synergies=[],
        handoffs=[],
        llm=fake_strategy_llm,
    )
    pri = [p.priority for p in plan.recommended_plays]
    assert pri == sorted(pri), "plays should arrive ordered by priority"


# ─── integration ──────────────────────────────────────────────────────────

def test_cascade_graph_produces_strategic_plan():
    brief = cascade_graph.run(sample_bundle(), **_FAKES)
    assert isinstance(brief, CascadeBrief)
    assert brief.strategic_plan is not None
    assert brief.strategic_plan.headline
    assert brief.strategic_plan.recommended_plays
    # executive_summary should now lean on the plan, not just templated counts
    assert brief.strategic_plan.headline.lower()[:10] in brief.executive_summary.lower() \
        or brief.executive_summary.startswith(brief.strategic_plan.headline)


def test_strategy_phase_events_emitted(tmp_path):
    events_file = tmp_path / "events.jsonl"
    cascade_graph.run(sample_bundle(), event_path=events_file, **_FAKES)
    events = [json.loads(l) for l in events_file.read_text().splitlines() if l.strip()]

    strategy_events = [e for e in events if e.get("phase") == "strategy"]
    assert len(strategy_events) >= 2, "expected start + done strategy events"

    statuses = {e.get("status") for e in strategy_events}
    assert "start" in statuses
    assert "done" in statuses

    # strategy must run AFTER cross_pollinate / handoff and BEFORE assemble
    handoff_idx = max(
        (i for i, e in enumerate(events) if e.get("phase") == "handoff"),
        default=-1,
    )
    strategy_start_idx = next(
        i for i, e in enumerate(events)
        if e.get("phase") == "strategy" and e.get("status") == "start"
    )
    assemble_idx = next(
        i for i, e in enumerate(events) if e.get("phase") == "assemble"
    )
    assert handoff_idx < strategy_start_idx < assemble_idx


def test_strategy_failure_is_contained():
    """A broken strategy LLM must not lose the rest of the cascade."""
    def broken_llm(_p):
        raise RuntimeError("LLM exploded")

    brief = cascade_graph.run(
        sample_bundle(),
        gtm_llm=fake_gtm_llm,
        finance_llm=fake_finance_llm,
        marketing_llm=fake_marketing_llm,
        security_llm=fake_security_llm,
        strategy_llm=broken_llm,
    )
    # brief still assembled, just without a plan
    assert isinstance(brief, CascadeBrief)
    assert brief.strategic_plan is None
    # depts still produced their outputs
    assert brief.account_brief and brief.market_signal and brief.risk_profile
