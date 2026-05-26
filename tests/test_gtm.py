from agents import gtm
from agents.schemas import AccountBrief
from guardrails.grounding import filter_claims
from fixtures.fake_llm import fake_gtm_llm
from fixtures.sample import sample_bundle


def test_gtm_produces_account_brief():
    brief = gtm.analyze(sample_bundle(), llm=fake_gtm_llm)
    assert isinstance(brief, AccountBrief)
    assert brief.target == "Northwind Analytics"
    assert len(brief.hiring_signals) >= 1
    assert len(brief.buying_signals) >= 1
    assert brief.outreach_angle


def test_gtm_claims_are_grounded():
    bundle = sample_bundle()
    brief = gtm.analyze(bundle, llm=fake_gtm_llm)
    kept, dropped = filter_claims(brief.all_claims(), bundle)
    assert dropped == []  # every fixture claim cites a real snippet
    assert kept, "expected at least one grounded claim"
