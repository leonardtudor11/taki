"""V7.10 — Pydantic auto-coerce singleton → list.

Regression for the actual real-LLM payload the user hit on the orchid.eu
self-mode run, where the model returned a bare dict for every MarketingSignal
field instead of `[{...}]`. The schema now wraps the singletons so the
cascade doesn't blow up on minor LLM JSON-shape drift.
"""

import pytest
from pydantic import ValidationError

from agents.schemas import (
    AccountBrief,
    Claim,
    HandoffMessage,
    MarketingSignal,
    MarketSignal,
    RiskProfile,
    StrategicPlan,
    StrategicPlay,
    SynergySignal,
)


# ─── the actual payload from the user's failed run ───────────────────────

ORCHID_PAYLOAD = {
    "target": "Orchid SRL",
    "value_proposition": {
        "text": "Your website communicates a clear focus on premium wind turbines.",
        "citations": [{
            "url": "https://orchid.eu",
            "snippet": "premium wind turbines for the European market",
            "source_type": "site",
        }],
        "confidence": 0.9,
    },
    "positioning": {
        "text": "You are positioning as a premium alternative to mass-market vendors.",
        "citations": [{
            "url": "https://orchid.eu",
            "snippet": "premium alternative",
            "source_type": "site",
        }],
    },
    "brand_voice": {
        "text": "Your brand voice is technical-precise.",
        "citations": [{
            "url": "https://orchid.eu",
            "snippet": "technical-precise",
            "source_type": "site",
        }],
    },
    "content_gaps": [
        {
            "text": "Homepage doesn't list customer case studies",
            "citations": [{
                "url": "https://orchid.eu",
                "snippet": "premium wind turbines",
                "source_type": "site",
            }],
        },
    ],
    "channel_signals": {
        "text": "Your primary channel is direct sales — no partner program visible.",
        "citations": [{
            "url": "https://orchid.eu",
            "snippet": "direct sales",
            "source_type": "site",
        }],
    },
}


def test_marketing_signal_accepts_bare_dict_for_list_fields():
    """Previously raised ValidationError × 4 (value_proposition, positioning,
    brand_voice, channel_signals). Should now coerce each into a 1-element list."""
    sig = MarketingSignal.model_validate(ORCHID_PAYLOAD)
    assert sig.target == "Orchid SRL"
    assert isinstance(sig.value_proposition, list) and len(sig.value_proposition) == 1
    assert isinstance(sig.positioning, list)        and len(sig.positioning)        == 1
    assert isinstance(sig.brand_voice, list)        and len(sig.brand_voice)        == 1
    assert isinstance(sig.content_gaps, list)       and len(sig.content_gaps)       == 1
    assert isinstance(sig.channel_signals, list)    and len(sig.channel_signals)    == 1
    # the wrapped claim survives intact
    assert sig.value_proposition[0].text.startswith("Your website")


# ─── other coercion cases ────────────────────────────────────────────────

def test_other_dept_schemas_wrap_singletons():
    """AccountBrief / MarketSignal / RiskProfile must also accept bare dicts."""
    ab = AccountBrief.model_validate({
        "target": "X",
        "buying_signals": {"text": "they raised a round", "citations": [], "confidence": 0.7},
    })
    assert isinstance(ab.buying_signals, list) and len(ab.buying_signals) == 1

    ms = MarketSignal.model_validate({
        "target": "X",
        "pricing_trend": {"text": "raised prices", "citations": []},
    })
    assert isinstance(ms.pricing_trend, list) and len(ms.pricing_trend) == 1

    rp = RiskProfile.model_validate({
        "target": "X",
        "exposure_indicators": {"text": "EU→US transfers", "citations": []},
    })
    assert isinstance(rp.exposure_indicators, list) and len(rp.exposure_indicators) == 1


def test_strategic_plan_wraps_singleton_play():
    """LLM might return a single play instead of a list — coerce."""
    plan = StrategicPlan.model_validate({
        "target": "X",
        "headline": "do this thing",
        "recommended_plays": {
            "text": "ship pricing page", "priority": 1,
            "timeframe": "this week", "owners": ["marketing"],
            "citations": [],
        },
        "open_questions": "what is the deal size?",
    })
    assert isinstance(plan.recommended_plays, list) and len(plan.recommended_plays) == 1
    assert isinstance(plan.open_questions, list) and len(plan.open_questions) == 1
    assert plan.open_questions[0] == "what is the deal size?"


def test_handoff_message_wraps_singleton_ref():
    h = HandoffMessage.model_validate({
        "from_dept": "finance", "to_dept": "gtm",
        "message": "pricing changed",
        "refs": "https://x/pricing",
    })
    assert h.refs == ["https://x/pricing"]


def test_synergy_signal_wraps_singletons():
    s = SynergySignal.model_validate({
        "text": "churn risk",
        "contributing_depts": "finance",
        "citations": {"url": "https://x", "snippet": "raised prices and complaints"},
    })
    assert s.contributing_depts == ["finance"]
    assert isinstance(s.citations, list) and len(s.citations) == 1


def test_list_field_with_none_becomes_empty_list():
    ab = AccountBrief.model_validate({
        "target": "X",
        "buying_signals": None,
    })
    assert ab.buying_signals == []


def test_scalar_passed_for_list_of_claim_still_errors():
    """Non-coercible scalars (int, float, bool) for list[Claim] still raise
    Pydantic's standard list-type error — the coercer only wraps dict/str."""
    with pytest.raises(ValidationError):
        AccountBrief.model_validate({"target": "X", "buying_signals": 42})


# ─── V7.15 — parse_into unwraps {"ClassName": {...}} double-wrap ─────────

def test_parse_into_unwraps_schema_named_wrapper():
    """LLMs occasionally return `{"RiskProfile": {...}}` instead of `{...}`.
    parse_into unwraps that once, case- and underscore-insensitive."""
    import json as _json
    from agents.base import parse_into

    inner = {
        "target": "X",
        "exposure_indicators": [],
        "reputational_signals": [],
        "regulatory_signals": [],
        "third_party_risk": [],
    }
    rp = parse_into(_json.dumps({"RiskProfile": inner}), RiskProfile)
    assert rp.target == "X"
    rp = parse_into(_json.dumps({"risk_profile": inner}), RiskProfile)
    assert rp.target == "X"
    rp = parse_into(_json.dumps({"riskprofile": inner}), RiskProfile)
    assert rp.target == "X"


def test_parse_into_does_not_unwrap_unrelated_keys():
    """If the single top-level key doesn't match the class name, the original
    ValidationError surfaces — we don't blindly unwrap."""
    import json as _json
    from agents.base import parse_into

    with pytest.raises(ValidationError):
        parse_into(_json.dumps({"unrelated": {"target": "X"}}), RiskProfile)


def test_parse_into_lifts_wrapped_sibling_target():
    """Real LLM payload seen on Supabase live run — wrapped RiskProfile sits
    alongside a sibling `target` key. Lift wrapped content into top-level,
    outer keys win on conflict."""
    import json as _json
    from agents.base import parse_into

    payload = {
        "RiskProfile": {
            "target": "WRONG_INNER",         # outer should win
            "exposure_indicators": [],
            "reputational_signals": [],
            "regulatory_signals": [],
            "third_party_risk": [],
        },
        "target": "Supabase",                # outer
    }
    rp = parse_into(_json.dumps(payload), RiskProfile)
    assert rp.target == "Supabase"           # outer beat inner
