from agents import orchestrator
from agents.schemas import AccountBrief, MarketSignal, RiskProfile
from fixtures.fake_llm import fake_finance_llm, fake_gtm_llm, fake_security_llm
from fixtures.sample import sample_bundle


def test_run_departments_collects_all_three():
    out = orchestrator.run_departments(
        sample_bundle(),
        gtm_llm=fake_gtm_llm,
        finance_llm=fake_finance_llm,
        security_llm=fake_security_llm,
    )
    assert isinstance(out.account_brief, AccountBrief)
    assert isinstance(out.market_signal, MarketSignal)
    assert isinstance(out.risk_profile, RiskProfile)
    assert out.account_brief.target == "Northwind Analytics"
