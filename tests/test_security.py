from agents import security
from agents.schemas import RiskProfile
from guardrails.grounding import filter_claims
from fixtures.fake_llm import fake_security_llm
from fixtures.sample import sample_bundle


def test_security_produces_risk_profile():
    rp = security.analyze(sample_bundle(), llm=fake_security_llm)
    assert isinstance(rp, RiskProfile)
    assert rp.target == "Northwind Analytics"
    assert len(rp.reputational_signals) >= 1
    assert len(rp.regulatory_signals) >= 1


def test_security_claims_grounded():
    bundle = sample_bundle()
    rp = security.analyze(bundle, llm=fake_security_llm)
    _, dropped = filter_claims(rp.all_claims(), bundle)
    assert dropped == []
