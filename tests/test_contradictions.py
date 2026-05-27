"""V7.23 — Contradictions agent tests.

Covers:
  - Citations get attached from parent claims by claim-text match
  - Contradictions w/o citation evidence on either side are dropped
  - Bad LLM output (non-JSON, wrong shape) returns empty list
  - End-to-end cascade plumbs contradictions into the brief
"""

from __future__ import annotations

import json

from agents.contradictions import analyze
from agents.schemas import (
    AccountBrief,
    Citation,
    Claim,
    Contradiction,
    MarketSignal,
    MarketingSignal,
    RiskProfile,
    SourceType,
)


def _claim(text: str, url: str, snippet: str) -> Claim:
    return Claim(
        text=text,
        citations=[Citation(url=url, snippet=snippet, source_type=SourceType.SITE)],
        confidence=0.8,
    )


def _ab() -> AccountBrief:
    return AccountBrief(
        target="X",
        buying_signals=[_claim("Industry-leading 99.99% uptime per the trust page.",
                              "https://x.com/trust", "99.99% uptime SLA")],
    )


def _ms() -> MarketSignal:
    return MarketSignal(target="X")


def _rp() -> RiskProfile:
    return RiskProfile(
        target="X",
        reputational_signals=[_claim("Reported 10 days of cumulative downtime in Q1 2026.",
                                    "https://reddit.com/r/X/downtime", "10 days of downtime")],
    )


def test_attaches_citations_from_parent_claims():
    """LLM returns claim_a + claim_b by text only; agent looks up + attaches
    the citations from the matching parent claims."""
    canned_llm = lambda _: json.dumps({
        "contradictions": [{
            "axis": "uptime",
            "claim_a": "Industry-leading 99.99% uptime per the trust page.",
            "claim_b": "Reported 10 days of cumulative downtime in Q1 2026.",
            "severity": 3,
            "summary": "Marketing uptime promise contradicts community-reported downtime.",
        }],
    })
    out = analyze(
        target="X",
        account_brief=_ab(),
        market_signal=_ms(),
        risk_profile=_rp(),
        llm=canned_llm,
    )
    assert len(out) == 1
    c = out[0]
    assert c.axis == "uptime"
    assert c.severity == 3
    assert len(c.citations_a) == 1
    assert c.citations_a[0].url == "https://x.com/trust"
    assert len(c.citations_b) == 1
    assert c.citations_b[0].url == "https://reddit.com/r/X/downtime"


def test_drops_contradictions_without_evidence():
    """LLM hallucinates a claim_b text not in the dept outputs — drop."""
    canned_llm = lambda _: json.dumps({
        "contradictions": [{
            "axis": "fake",
            "claim_a": "Industry-leading 99.99% uptime per the trust page.",  # real
            "claim_b": "Acquired by Globex next week.",                        # not in any claim
            "severity": 3,
            "summary": "imaginary",
        }],
    })
    out = analyze(
        target="X",
        account_brief=_ab(),
        market_signal=_ms(),
        risk_profile=_rp(),
        llm=canned_llm,
    )
    assert out == []


def test_malformed_llm_output_returns_empty():
    """Non-JSON output from the LLM → []. Don't crash the cascade."""
    out = analyze(
        target="X",
        account_brief=_ab(),
        market_signal=_ms(),
        risk_profile=_rp(),
        llm=lambda _: "not json at all",
    )
    assert out == []


def test_handles_bare_list_envelope():
    """Some LLMs return a bare list instead of {'contradictions': [...]}."""
    canned_llm = lambda _: json.dumps([{
        "axis": "uptime",
        "claim_a": "Industry-leading 99.99% uptime per the trust page.",
        "claim_b": "Reported 10 days of cumulative downtime in Q1 2026.",
        "severity": 2,
        "summary": "tension",
    }])
    out = analyze(
        target="X",
        account_brief=_ab(),
        market_signal=_ms(),
        risk_profile=_rp(),
        llm=canned_llm,
    )
    assert len(out) == 1


def test_severity_coerced_to_clamp_1_3():
    canned_llm = lambda _: json.dumps({
        "contradictions": [{
            "axis": "uptime",
            "claim_a": "Industry-leading 99.99% uptime per the trust page.",
            "claim_b": "Reported 10 days of cumulative downtime in Q1 2026.",
            "severity": "major",  # string keyword
            "summary": "x",
        }],
    })
    out = analyze(
        target="X",
        account_brief=_ab(),
        market_signal=_ms(),
        risk_profile=_rp(),
        llm=canned_llm,
    )
    assert out[0].severity == 3


def test_returns_empty_when_under_two_claims():
    """No contradictions possible with <2 claims — skip the LLM call entirely."""
    out = analyze(
        target="X",
        account_brief=AccountBrief(target="X"),  # zero claims
        market_signal=_ms(),
        risk_profile=RiskProfile(target="X"),    # zero claims
        llm=lambda _: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    assert out == []
