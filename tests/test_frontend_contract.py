"""Ensures frontend/brief.json carries every field app.js reads.

This is the offline stand-in for a browser render check; a human/Playwright
pass still confirms visual layout.
"""

import json
from pathlib import Path

BRIEF = Path(__file__).resolve().parent.parent / "frontend" / "brief.json"


def test_brief_json_exists():
    assert BRIEF.exists(), "frontend/brief.json missing"


def test_brief_has_fields_app_js_reads():
    b = json.loads(BRIEF.read_text())
    for k in ("target", "executive_summary", "guardrail_report",
              "synergy_signals", "account_brief", "market_signal",
              "risk_profile", "handoffs"):
        assert k in b, f"missing top-level key: {k}"

    r = b["guardrail_report"]
    for k in ("pii_redactions", "leak_flags", "ungrounded_dropped", "passed"):
        assert k in r, f"guardrail_report missing: {k}"

    for k in ("buying_signals", "competitor_moves", "hiring_signals"):
        assert k in b["account_brief"]
    for k in ("pricing_trend", "expansion_contraction",
              "web_traffic_proxy", "vendor_health_flags"):
        assert k in b["market_signal"]
    for k in ("exposure_indicators", "reputational_signals",
              "regulatory_signals", "third_party_risk"):
        assert k in b["risk_profile"]


def test_synergy_and_claim_shape():
    b = json.loads(BRIEF.read_text())
    assert b["synergy_signals"], "expected synergies in example brief"
    s = b["synergy_signals"][0]
    assert "contributing_depts" in s and "text" in s

    claim = b["account_brief"]["hiring_signals"][0]
    assert "text" in claim and "citations" in claim
    assert "url" in claim["citations"][0]


def test_handoff_shape_for_cascade_flow():
    b = json.loads(BRIEF.read_text())
    assert b["handoffs"], "expected handoffs in example brief"
    h = b["handoffs"][0]
    for k in ("from_dept", "to_dept", "message"):
        assert k in h, f"handoff missing: {k}"
