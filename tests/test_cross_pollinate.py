from agents import orchestrator
from fixtures.fake_llm import fake_finance_llm, fake_gtm_llm, fake_security_llm
from fixtures.sample import sample_bundle


def _outputs():
    return orchestrator.run_departments(
        sample_bundle(),
        gtm_llm=fake_gtm_llm,
        finance_llm=fake_finance_llm,
        security_llm=fake_security_llm,
    )


def test_synergy_references_two_departments():
    synergies, _ = orchestrator.cross_pollinate(_outputs())
    assert synergies, "expected at least one synergy signal"
    for s in synergies:
        assert len(s.contributing_depts) >= 2


def test_handoffs_emitted_across_departments():
    _, handoffs = orchestrator.cross_pollinate(_outputs())
    pairs = {(h.from_dept, h.to_dept) for h in handoffs}
    # fixture has pricing, reputational, and hiring signals -> 3 handoffs
    assert ("finance", "gtm") in pairs
    assert ("security", "gtm") in pairs
    assert ("gtm", "security") in pairs


def test_synergy_churn_risk_present():
    synergies, _ = orchestrator.cross_pollinate(_outputs())
    texts = " ".join(s.text for s in synergies).lower()
    assert "churn risk" in texts
