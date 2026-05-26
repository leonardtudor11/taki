"""V7 — marketing department unit + integration tests."""

from agents import marketing
from agents.schemas import (
    BusinessProfile,
    CascadeMode,
    MarketingSignal,
    Stage,
)
from guardrails.grounding import filter_claims
from fixtures.fake_llm import fake_marketing_llm
from fixtures.sample import sample_bundle


def test_marketing_returns_signal_target_mode():
    sig = marketing.analyze(sample_bundle(), llm=fake_marketing_llm)
    assert isinstance(sig, MarketingSignal)
    assert sig.target == "Northwind Analytics"
    assert len(sig.value_proposition) >= 1
    assert len(sig.positioning) >= 1
    assert len(sig.content_gaps) >= 1


def test_marketing_returns_signal_self_mode():
    profile = BusinessProfile(
        name="Northwind Analytics",
        url="https://northwind.example/",
        industry="B2B analytics",
        stage=Stage.GROWTH,
        goal="Win 50 EU enterprise logos",
        customer_segment="Mid-market RevOps + Finance",
    )
    sig = marketing.analyze(
        sample_bundle(),
        llm=fake_marketing_llm,
        mode=CascadeMode.SELF,
        business_context=f"name: {profile.name}\nurl: {profile.url}",
    )
    assert isinstance(sig, MarketingSignal)
    assert sig.all_claims(), "expected grounded claims in self-mode"


def test_marketing_claims_are_grounded():
    bundle = sample_bundle()
    sig = marketing.analyze(bundle, llm=fake_marketing_llm)
    _, dropped = filter_claims(sig.all_claims(), bundle)
    assert dropped == [], f"expected all claims grounded, dropped: {dropped}"
