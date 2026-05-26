from agents.schemas import (
    AccountBrief,
    CascadeBrief,
    Citation,
    Claim,
    GuardrailReport,
    HandoffMessage,
    MarketSignal,
    RiskProfile,
    SourceType,
    SynergySignal,
)
from fixtures.sample import sample_bundle


def test_bundle_fixture_validates():
    b = sample_bundle()
    assert b.target == "Northwind Analytics"
    assert len(b.sources) == 5
    assert all(s.url.startswith("http") for s in b.sources)
    assert len(b.texts()) == 5


def test_claim_with_citation():
    c = Claim(
        text="Pro plan rose to $79/seat.",
        citations=[
            Citation(
                url="https://northwind.example/pricing",
                snippet="raised its Pro plan from $49 to $79",
                source_type=SourceType.PRICING,
            )
        ],
        confidence=0.9,
    )
    assert c.citations[0].source_type == SourceType.PRICING
    assert 0.0 <= c.confidence <= 1.0


def test_department_outputs_aggregate_claims():
    claim = Claim(text="x")
    ab = AccountBrief(target="t", buying_signals=[claim], hiring_signals=[claim])
    ms = MarketSignal(target="t", pricing_trend=[claim])
    rp = RiskProfile(target="t", exposure_indicators=[claim])
    assert len(ab.all_claims()) == 2
    assert len(ms.all_claims()) == 1
    assert len(rp.all_claims()) == 1


def test_cascade_brief_composes():
    brief = CascadeBrief(
        target="t",
        account_brief=AccountBrief(target="t"),
        market_signal=MarketSignal(target="t"),
        risk_profile=RiskProfile(target="t"),
        synergy_signals=[SynergySignal(text="combined", contributing_depts=["gtm", "finance"])],
        handoffs=[HandoffMessage(from_dept="finance", to_dept="gtm", message="timing")],
        guardrail_report=GuardrailReport(passed=True),
        executive_summary="ok",
    )
    # round-trips through JSON without loss
    again = CascadeBrief.model_validate_json(brief.model_dump_json())
    assert again.synergy_signals[0].contributing_depts == ["gtm", "finance"]
    assert again.handoffs[0].from_dept == "finance"
