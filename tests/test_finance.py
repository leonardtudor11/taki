from agents import finance
from agents.schemas import MarketSignal
from guardrails.grounding import filter_claims
from fixtures.fake_llm import fake_finance_llm
from fixtures.sample import sample_bundle


def test_finance_produces_market_signal():
    sig = finance.analyze(sample_bundle(), llm=fake_finance_llm)
    assert isinstance(sig, MarketSignal)
    assert sig.target == "Northwind Analytics"
    assert len(sig.pricing_trend) == 1


def test_finance_claims_grounded():
    bundle = sample_bundle()
    sig = finance.analyze(bundle, llm=fake_finance_llm)
    _, dropped = filter_claims(sig.all_claims(), bundle)
    assert dropped == []
