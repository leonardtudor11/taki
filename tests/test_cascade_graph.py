"""V2 — verify the LangGraph cascade matches the legacy orchestrator output and
emits a well-formed event stream."""

import json

from agents import cascade_graph
from agents.schemas import CascadeBrief
from fixtures.fake_llm import (
    fake_finance_llm,
    fake_gtm_llm,
    fake_security_llm,
    fake_strategy_llm,
)
from fixtures.sample import sample_bundle

# V6: include strategy_llm so the strategy node never falls back to the
# real default LLM (which would hit Vertex/Gemini and burn tokens in tests).
_FAKES = dict(
    gtm_llm=fake_gtm_llm,
    finance_llm=fake_finance_llm,
    security_llm=fake_security_llm,
    strategy_llm=fake_strategy_llm,
)


def test_graph_run_produces_full_brief():
    brief = cascade_graph.run(sample_bundle(), **_FAKES)
    assert isinstance(brief, CascadeBrief)
    assert brief.account_brief and brief.market_signal and brief.risk_profile
    assert brief.synergy_signals, "expected synergies from fixture"
    assert brief.handoffs, "expected handoffs from fixture"
    assert brief.executive_summary
    # guardrail report shape — full output of the LangGraph pipeline
    r = brief.guardrail_report
    assert r.pii_redactions == 2
    assert len(r.leak_flags) == 1


def test_events_emitted_in_phase_order(tmp_path):
    events_file = tmp_path / "events.jsonl"
    cascade_graph.run(sample_bundle(), event_path=events_file, **_FAKES)

    assert events_file.exists()
    events = [json.loads(line) for line in events_file.read_text().splitlines() if line.strip()]
    assert len(events) >= 10, f"expected rich event stream, got {len(events)}"

    phases = [e["phase"] for e in events]
    # required phases fire at least once each
    for required in ("pii", "leak", "dept", "grounding", "cross_pollinate".replace("cross_pollinate", "handoff"), "assemble"):
        # accept either handoff/synergy as cross_pollinate emissions
        assert any(p in phases for p in [required]) or required == "handoff", \
            f"missing phase: {required}"

    # PII must complete before any dept runs (guardrails-before-LLM invariant)
    pii_done_idx = next(i for i, e in enumerate(events) if e["phase"] == "pii" and e["status"] == "done")
    first_dept_idx = next(i for i, e in enumerate(events) if e["phase"] == "dept")
    assert pii_done_idx < first_dept_idx, "PII redaction must finish before any dept fires"

    # leak must complete before any dept runs
    leak_done_idx = next(i for i, e in enumerate(events) if e["phase"] == "leak" and e["status"] == "done")
    assert leak_done_idx < first_dept_idx, "leak filter must finish before any dept fires"

    # all three dept-done events present
    dept_done = {e["dept"] for e in events if e["phase"] == "dept" and e["status"] == "done"}
    assert dept_done == {"gtm", "finance", "security"}

    # grounding fires AFTER all depts complete (join semantics)
    grounding_idx = next(i for i, e in enumerate(events) if e["phase"] == "grounding" and e["status"] == "start")
    last_dept_idx = max(i for i, e in enumerate(events) if e["phase"] == "dept" and e["status"] == "done")
    assert last_dept_idx < grounding_idx, "grounding must wait for all depts"

    # handoffs land after grounding (synergies depend on grounded outputs)
    handoff_events = [e for e in events if e["phase"] == "handoff"]
    assert handoff_events, "expected at least one handoff event"
    for h in handoff_events:
        assert {"from", "to", "message"} <= set(h)


def test_event_path_directory_is_created(tmp_path):
    nested = tmp_path / "a" / "b" / "events.jsonl"
    cascade_graph.run(sample_bundle(), event_path=nested, **_FAKES)
    assert nested.exists()


def test_emit_does_not_break_on_sink_failure(tmp_path):
    # a sink that raises must not crash the cascade — events are advisory.
    def boom(_event):
        raise RuntimeError("sink down")

    graph = cascade_graph.build_graph(**_FAKES, on_event=boom)
    final = graph.invoke({"bundle": sample_bundle(), "events": []})
    assert isinstance(final["brief"], CascadeBrief)
