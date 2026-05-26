from agents import orchestrator
from agents.schemas import CascadeBrief
from fixtures.fake_llm import (
    fake_finance_llm,
    fake_gtm_llm,
    fake_gtm_llm_with_hallucination,
    fake_security_llm,
)
from fixtures.sample import sample_bundle


def _build(gtm_llm):
    return orchestrator.build_cascade_brief(
        sample_bundle(),
        gtm_llm=gtm_llm,
        finance_llm=fake_finance_llm,
        security_llm=fake_security_llm,
    )


def test_end_to_end_cascade_brief():
    brief = _build(fake_gtm_llm)
    assert isinstance(brief, CascadeBrief)
    assert brief.account_brief and brief.market_signal and brief.risk_profile
    assert brief.synergy_signals
    assert brief.handoffs
    assert brief.executive_summary


def test_guardrails_fire_in_flow():
    brief = _build(fake_gtm_llm)
    r = brief.guardrail_report
    # PII redaction ran before leak withholding -> email + phone scrubbed
    assert r.pii_redactions == 2
    # the CONFIDENTIAL contact source was withheld
    assert len(r.leak_flags) == 1
    assert "contact" in r.leak_flags[0]


def test_planted_hallucination_is_dropped():
    brief = _build(fake_gtm_llm_with_hallucination)
    # the uncited Globex claim must not survive into the brief
    texts = " ".join(c.text for c in brief.account_brief.all_claims())
    assert "Globex" not in texts
    assert any("Globex" in d for d in brief.guardrail_report.ungrounded_dropped)


def test_passed_flag_reflects_grounding():
    clean = _build(fake_gtm_llm)
    assert clean.guardrail_report.passed is True
    halluc = _build(fake_gtm_llm_with_hallucination)
    assert halluc.guardrail_report.passed is False
