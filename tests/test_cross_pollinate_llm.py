"""V7.35 — LLM-driven cross-pollinate.

Pins the contract: LLM output is preferred when non-empty; empty/parse
failures fall back to the V7.0 templated cross_pollinate. URLs in
handoff refs + synergy citations are filtered against the claim URLs
the LLM was actually shown (defence against URL hallucination).
"""

from __future__ import annotations

import json

from agents import cross_pollinate_llm
from agents.schemas import (
    AccountBrief,
    BusinessProfile,
    Citation,
    Claim,
    HandoffMessage,
    MarketSignal,
    MarketingSignal,
    RiskProfile,
    Sector,
    SynergySignal,
)


def _claim(text: str, url: str, snippet: str = "") -> Claim:
    return Claim(
        text=text,
        citations=[Citation(url=url, snippet=snippet or text[:40])],
    )


def _signals() -> tuple[AccountBrief, MarketSignal, MarketingSignal, RiskProfile]:
    ab = AccountBrief(
        target="Northwind Analytics",
        buying_signals=[_claim("Posted RFP for ML platform on Q2", "https://northwind.example/rfp")],
        hiring_signals=[_claim("Hiring 12 enterprise AEs", "https://northwind.example/careers")],
    )
    ms = MarketSignal(
        target="Northwind Analytics",
        pricing_trend=[_claim("Raised Pro tier from $49 to $79/seat in Mar", "https://northwind.example/pricing")],
        expansion_contraction=[_claim("Opened EU office in Lisbon", "https://northwind.example/about")],
    )
    mk = MarketingSignal(target="Northwind Analytics")
    rp = RiskProfile(
        target="Northwind Analytics",
        reputational_signals=[_claim("G2 review average dipped from 4.6 to 4.3", "https://g2.example/northwind")],
    )
    return ab, ms, mk, rp


def _profile() -> BusinessProfile:
    return BusinessProfile(
        name="Northwind Analytics",
        url="https://northwind.example",
        industry="enterprise data analytics SaaS",
        stage="growth",
        customer_segment="mid-market data teams",
        competitor_names=["Acme Insights", "Globex DataOps"],
    )


def test_analyze_returns_empty_when_all_signals_none():
    h, s = cross_pollinate_llm.analyze(
        account_brief=None, market_signal=None, marketing_signal=None,
        risk_profile=None, business_profile=None, sector=None,
        sector_signal=None, target="X",
    )
    assert h == [] and s == []


def test_analyze_returns_llm_handoffs_and_synergies():
    from fixtures.fake_llm import fake_cross_pollinate_llm
    ab, ms, mk, rp = _signals()
    handoffs, synergies = cross_pollinate_llm.analyze(
        account_brief=ab, market_signal=ms, marketing_signal=mk, risk_profile=rp,
        business_profile=_profile(), sector=None, sector_signal=None,
        target="Northwind Analytics", llm=fake_cross_pollinate_llm,
    )
    assert len(handoffs) == 2
    assert all(isinstance(h, HandoffMessage) for h in handoffs)
    # Personalized content: mentions the actual $49→$79 fact
    joined = " ".join(h.message for h in handoffs)
    assert "$49" in joined and "$79" in joined
    # Synergy mentions enterprise bundle pivot
    assert len(synergies) == 1
    assert isinstance(synergies[0], SynergySignal)
    assert "enterprise" in synergies[0].text.lower()


def test_analyze_filters_hallucinated_urls():
    """LLM emits ref URLs that weren't in the shown claims — filtered out."""
    def llm(_p):
        return json.dumps({
            "handoffs": [{
                "from_dept": "finance", "to_dept": "gtm",
                "message": "Real message about pricing.",
                "refs": [
                    "https://northwind.example/pricing",   # real, in claims
                    "https://hallucinated.example/fake",   # NOT in shown claims
                ],
            }],
            "synergies": [{
                "text": "Real synergy text combining two depts.",
                "contributing_depts": ["finance", "security"],
                "citations": [
                    {"url": "https://northwind.example/pricing", "snippet": "real", "source_type": "pricing"},
                    {"url": "https://made-up.example/x",        "snippet": "fake", "source_type": "other"},
                ],
            }],
        })
    ab, ms, mk, rp = _signals()
    handoffs, synergies = cross_pollinate_llm.analyze(
        account_brief=ab, market_signal=ms, marketing_signal=mk, risk_profile=rp,
        business_profile=_profile(), sector=None, sector_signal=None,
        target="Northwind Analytics", llm=llm,
    )
    assert handoffs[0].refs == ["https://northwind.example/pricing"]
    # Hallucinated citation URL dropped; real one kept.
    citation_urls = [c.url for c in synergies[0].citations]
    assert citation_urls == ["https://northwind.example/pricing"]


def test_analyze_caps_at_max_handoffs_and_synergies():
    """LLM over-emits → output capped at MAX_HANDOFFS / MAX_SYNERGIES."""
    def llm(_p):
        return json.dumps({
            "handoffs": [
                {"from_dept": "finance", "to_dept": "gtm",
                 "message": f"H{i} message", "refs": ["https://northwind.example/pricing"]}
                for i in range(20)
            ],
            "synergies": [
                {"text": f"S{i} synergy", "contributing_depts": ["finance", "security"], "citations": []}
                for i in range(20)
            ],
        })
    ab, ms, mk, rp = _signals()
    handoffs, synergies = cross_pollinate_llm.analyze(
        account_brief=ab, market_signal=ms, marketing_signal=mk, risk_profile=rp,
        business_profile=_profile(), sector=None, sector_signal=None,
        target="Northwind Analytics", llm=llm,
    )
    assert len(handoffs)  == cross_pollinate_llm.MAX_HANDOFFS
    assert len(synergies) == cross_pollinate_llm.MAX_SYNERGIES


def test_analyze_drops_self_handoff_and_empty_messages():
    def llm(_p):
        return json.dumps({
            "handoffs": [
                {"from_dept": "gtm", "to_dept": "gtm",  "message": "Self-handoff", "refs": []},
                {"from_dept": "finance", "to_dept": "gtm", "message": "",            "refs": []},
                {"from_dept": "finance", "to_dept": "gtm", "message": "Real handoff", "refs": []},
            ],
            "synergies": [
                {"text": "Synergy w/ only one dept",  "contributing_depts": ["finance"],          "citations": []},
                {"text": "Synergy w/ no depts",        "contributing_depts": [],                   "citations": []},
                {"text": "Real synergy",                "contributing_depts": ["finance", "gtm"], "citations": []},
            ],
        })
    ab, ms, mk, rp = _signals()
    h, s = cross_pollinate_llm.analyze(
        account_brief=ab, market_signal=ms, marketing_signal=mk, risk_profile=rp,
        business_profile=_profile(), sector=None, sector_signal=None,
        target="Northwind Analytics", llm=llm,
    )
    assert len(h) == 1 and h[0].message == "Real handoff"
    assert len(s) == 1 and s[0].text == "Real synergy"


def test_analyze_returns_empty_on_malformed_json():
    def llm(_p): return "not json at all"
    ab, ms, mk, rp = _signals()
    h, s = cross_pollinate_llm.analyze(
        account_brief=ab, market_signal=ms, marketing_signal=mk, risk_profile=rp,
        business_profile=_profile(), sector=None, sector_signal=None,
        target="Northwind Analytics", llm=llm,
    )
    assert h == [] and s == []


def test_analyze_returns_empty_on_llm_exception():
    def llm(_p): raise RuntimeError("vertex 500")
    ab, ms, mk, rp = _signals()
    h, s = cross_pollinate_llm.analyze(
        account_brief=ab, market_signal=ms, marketing_signal=mk, risk_profile=rp,
        business_profile=_profile(), sector=None, sector_signal=None,
        target="Northwind Analytics", llm=llm,
    )
    assert h == [] and s == []
