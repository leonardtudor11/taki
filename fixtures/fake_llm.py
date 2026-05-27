"""Canned LLM responses for offline department tests.

Each fake returns JSON that matches a department schema and cites snippets that
exist in fixtures.sample.sample_bundle(), so grounding passes. V6 enriched
these to give the demo dashboard meaningful depth — multiple claims per
field, more comparative content, and a fake_strategy_llm that produces a
full StrategicPlan.
"""

from __future__ import annotations

import json

# ─── helpers ──────────────────────────────────────────────────────────────

def _claim(text, url, snippet, source_type, confidence=0.8):
    return {
        "text": text,
        "citations": [{"url": url, "snippet": snippet, "source_type": source_type}],
        "confidence": confidence,
    }


# ─── GTM ──────────────────────────────────────────────────────────────────

def fake_gtm_llm(_prompt: str) -> str:
    return json.dumps({
        "target": "Northwind Analytics",
        "buying_signals": [
            _claim(
                "Recently raised a $40M Series B to expand into the EU — fresh capital and a clear go-to-market mandate.",
                "https://news.example/northwind-series-b",
                "closed a $40M Series B led by Acme Ventures",
                "news",
                0.85,
            ),
            _claim(
                "Enterprise tier with SSO + SCIM signals a deliberate move up-market — they are buying enterprise tooling.",
                "https://northwind.example/pricing",
                "Enterprise tier adds SSO, SCIM, and a 99.9% SLA at $250 per seat",
                "pricing",
                0.8,
            ),
        ],
        "competitor_moves": [
            _claim(
                "Public positioning vs Tableau (time-to-first-insight) and Looker (per-seat pricing) — they are picking direct fights with incumbents.",
                "https://northwind.example/blog/why-us-vs-tableau",
                "outperform Tableau on time-to-first-insight by 3x",
                "site",
                0.75,
            ),
            _claim(
                "Targets ThoughtSpot's wedge (natural-language search) in head-to-head evaluations.",
                "https://northwind.example/blog/why-us-vs-tableau",
                "win evaluations against ThoughtSpot on natural-language search",
                "site",
                0.7,
            ),
        ],
        "hiring_signals": [
            _claim(
                "Scaling enterprise sales headcount — 12 AEs + 4 SEs across NA.",
                "https://northwind.example/careers",
                "hiring 12 enterprise account executives",
                "jobs",
                0.9,
            ),
            _claim(
                "EU expansion is staffed up — London + Berlin leadership roles open.",
                "https://news.example/northwind-series-b",
                "fund headcount in London and Berlin",
                "news",
                0.8,
            ),
            _claim(
                "Building a partner-led motion — new VP of Channel Partnerships role posted.",
                "https://northwind.example/careers",
                "VP of Channel Partnerships",
                "jobs",
                0.7,
            ),
        ],
        "outreach_angle": "Congratulate on the Series B; anchor on EU GTM + enterprise tier; differentiate on time-to-insight vs Tableau.",
    })


def fake_gtm_llm_with_hallucination(_prompt: str) -> str:
    """Same as fake_gtm_llm but adds one uncited/hallucinated claim.
    Used to prove the grounding guard drops it mid-cascade."""
    data = json.loads(fake_gtm_llm(_prompt))
    data["competitor_moves"].append(_claim(
        "Northwind is being acquired by Globex next week.",
        "https://made-up.example",
        "acquired by Globex next week",
        "news",
        0.99,
    ))
    return json.dumps(data)


# ─── Finance ──────────────────────────────────────────────────────────────

def fake_finance_llm(_prompt: str) -> str:
    return json.dumps({
        "target": "Northwind Analytics",
        "pricing_trend": [
            _claim(
                "Raised Pro pricing ~60% and dropped the free tier — clear pivot toward higher-ARPU customers.",
                "https://northwind.example/pricing",
                "raised its Pro plan from $49 to $79",
                "pricing",
                0.9,
            ),
            _claim(
                "Enterprise tier at $250/seat with SLA — signals willingness to price for procurement-led deals.",
                "https://northwind.example/pricing",
                "Enterprise tier adds SSO, SCIM, and a 99.9% SLA at $250 per seat",
                "pricing",
                0.85,
            ),
        ],
        "expansion_contraction": [
            _claim(
                "Series B funding tied to EU expansion — $40M growth capital deployed regionally.",
                "https://news.example/northwind-series-b",
                "closed a $40M Series B led by Acme Ventures",
                "news",
                0.85,
            ),
            _claim(
                "Headcount expansion: 12 AE + 4 SE across NA + new EU leadership — aggressive growth posture.",
                "https://northwind.example/careers",
                "hiring 12 enterprise account executives",
                "jobs",
                0.8,
            ),
            _claim(
                "Channel motion build-out (new VP) suggests indirect revenue is targeted to scale.",
                "https://northwind.example/careers",
                "VP of Channel Partnerships",
                "jobs",
                0.65,
            ),
        ],
        "web_traffic_proxy": [
            _claim(
                "Multiple G2 reviews recent enough to show meaningful customer activity — usage is healthy.",
                "https://reviews.example/northwind",
                "Several G2 reviewers cite billing surprises",
                "review",
                0.55,
            ),
        ],
        "vendor_health_flags": [
            _claim(
                "Heavy AWS + Snowflake dependency — concentration risk if either vendor renegotiates.",
                "https://northwind.example/trust/subprocessors",
                "AWS (hosting), Stripe (billing), Twilio (transactional email), Snowflake",
                "site",
                0.7,
            ),
        ],
    })


# ─── Security ─────────────────────────────────────────────────────────────

def fake_security_llm(_prompt: str) -> str:
    return json.dumps({
        "target": "Northwind Analytics",
        "exposure_indicators": [
            _claim(
                "EU→US data transfers under SCCs — exposure to Schrems II / DPF challenges.",
                "https://northwind.example/trust/subprocessors",
                "Customer data flows include EU→US transfers under SCCs",
                "site",
                0.75,
            ),
            _claim(
                "Stripe + Twilio in the subprocessor chain → payment + transactional-email attack surface.",
                "https://northwind.example/trust/subprocessors",
                "AWS (hosting), Stripe (billing), Twilio (transactional email)",
                "site",
                0.65,
            ),
        ],
        "reputational_signals": [
            _claim(
                "Support quality complaints and billing surprises follow the recent pricing change.",
                "https://reviews.example/northwind",
                "report slow support response times",
                "review",
                0.7,
            ),
            _claim(
                "Customer-facing churn risk surfaced in G2 reviews citing onboarding friction.",
                "https://reviews.example/northwind",
                "slower onboarding",
                "review",
                0.6,
            ),
        ],
        "regulatory_signals": [
            _claim(
                "SOC 2 Type II achieved + ISO 27001 in filing — compliance posture is strengthening.",
                "https://news.example/northwind-soc2",
                "Northwind Analytics announced SOC 2 Type II attestation",
                "news",
                0.85,
            ),
            _claim(
                "DPA update in flight for GDPR alignment — EU customers may want pre-signed terms.",
                "https://news.example/northwind-soc2",
                "preparing a DPA update for GDPR alignment",
                "news",
                0.75,
            ),
        ],
        "third_party_risk": [
            _claim(
                "AWS hosting concentration — single-region failure modes worth probing.",
                "https://northwind.example/trust/subprocessors",
                "AWS (hosting), Stripe (billing)",
                "site",
                0.65,
            ),
            _claim(
                "Snowflake as the analytics warehouse — supply-chain breach there cascades to customer data.",
                "https://northwind.example/trust/subprocessors",
                "Snowflake (analytics warehouse)",
                "site",
                0.7,
            ),
        ],
    })


# ─── Marketing (V7) ───────────────────────────────────────────────────────

def fake_marketing_llm(_prompt: str) -> str:
    """Marketing dept output grounded against the Northwind sample bundle.

    Mixes self-mode framing (content_gaps written as observations to fix) and
    target-mode framing (positioning/voice as observed) so it works for both
    test paths — the schema is the same, only the rationale tone differs.
    """
    return json.dumps({
        "target": "Northwind Analytics",
        "value_proposition": [
            _claim(
                "Site positions on enterprise-grade pricing + SLA + SSO/SCIM — strong procurement narrative.",
                "https://northwind.example/pricing",
                "Enterprise tier adds SSO, SCIM, and a 99.9% SLA at $250 per seat",
                "pricing",
                0.85,
            ),
            _claim(
                "Public comparative claim vs Tableau anchors on 'time-to-first-insight' — speed is the headline value-prop.",
                "https://northwind.example/blog/why-us-vs-tableau",
                "outperform Tableau on time-to-first-insight by 3x",
                "site",
                0.8,
            ),
        ],
        "positioning": [
            _claim(
                "Positioning is 'fast, enterprise-ready, undercuts incumbents on per-seat' — three direct comparisons with named competitors.",
                "https://northwind.example/blog/why-us-vs-tableau",
                "undercut Looker on per-seat pricing by roughly 40%",
                "site",
                0.8,
            ),
            _claim(
                "Enterprise wedge: SSO + SCIM + SLA, $250/seat — explicit procurement-grade tier.",
                "https://northwind.example/pricing",
                "Enterprise tier adds SSO, SCIM, and a 99.9% SLA at $250 per seat",
                "pricing",
                0.8,
            ),
        ],
        "brand_voice": [
            _claim(
                "Voice is direct and comparative — willingness to name competitors publicly is unusual and confident.",
                "https://northwind.example/blog/why-us-vs-tableau",
                "win evaluations against ThoughtSpot on natural-language search",
                "site",
                0.7,
            ),
        ],
        "content_gaps": [
            _claim(
                "No customer case studies surfaced — review-sourced testimonials are negative (support latency) without offsetting wins on site.",
                "https://reviews.example/northwind",
                "report slow support response times",
                "review",
                0.75,
            ),
            _claim(
                "Trust page lists subprocessors but does not link to SOC 2 / ISO 27001 attestation evidence — leaves procurement reviewers without the proof artifact.",
                "https://northwind.example/trust/subprocessors",
                "AWS (hosting), Stripe (billing), Twilio (transactional email)",
                "site",
                0.7,
            ),
            _claim(
                "Pricing page does not segment by customer type (e.g. SMB vs Enterprise narrative) — comparative copy lives in a blog instead of on /pricing.",
                "https://northwind.example/pricing",
                "raised its Pro plan from $49 to $79",
                "pricing",
                0.65,
            ),
        ],
        "channel_signals": [
            _claim(
                "Channel motion build-out: VP Channel Partnerships role open — partner channel is being designed, not yet live.",
                "https://northwind.example/careers",
                "VP of Channel Partnerships",
                "jobs",
                0.7,
            ),
        ],
    })


# ─── Strategy (V6) ────────────────────────────────────────────────────────

def fake_strategy_llm(_prompt: str) -> str:
    """Canned StrategicPlan — synthesized from the three dept outputs above.

    Every recommended_play cites a snippet that appears verbatim in the fake
    dept responses, so it would pass an LLM-level grounding sanity check.
    """
    return json.dumps({
        "target": "Northwind Analytics",
        "headline": "Funded EU-bound up-market analytics player — buy window is this quarter, lead with retention.",
        "narrative": (
            "Northwind just closed a $40M Series B with a clear EU mandate and is "
            "actively staffing London + Berlin alongside 12 NA enterprise AEs. The "
            "Pro tier pricing jumped ~60% and a $250/seat enterprise tier with SSO + "
            "SCIM + 99.9% SLA is now live — they are explicitly designing for procurement-led deals.\n\n"
            "Why now: capital + headcount + enterprise SKU all landed together. The new "
            "VP Channel Partnerships hire signals an indirect motion that will be slow "
            "to mature, which means direct outreach has a clear runway this quarter.\n\n"
            "Where the risk lives: the same review window that documents the pricing move "
            "also documents support latency and billing surprises — and reviews flag "
            "slower onboarding. SOC 2 Type II is fresh and ISO 27001 is filed, but EU→US "
            "data transfers under SCCs mean any procurement security review will "
            "scrutinize the subprocessor chain (AWS, Stripe, Twilio, Snowflake)."
        ),
        "icp_fit": "high",
        "icp_rationale": "Funded, hiring enterprise sellers, shipping an enterprise SKU with SSO/SCIM — exactly the profile that buys enterprise tooling this year.",
        "deal_size_estimate": "$120k-$320k ARR (year 1)",
        "deal_size_rationale": "20-40 seats at the new $250/seat enterprise tier; growth corridor through EU headcount build supports doubling within 18 months.",
        "urgency": "act this quarter",
        "urgency_rationale": "Series B announcements close the easiest intro window; channel motion is months away, so direct now beats indirect later.",
        "recommended_plays": [
            {
                "text": "Open at the CRO with a Series-B congratulatory note that anchors on EU expansion staffing; offer a 30-min EU-region case study.",
                "priority": 1,
                "timeframe": "this week",
                "owners": ["gtm"],
                "rationale": "Capital + EU hiring narrative is fresh and quotable; channel partnerships hire confirms direct sales is still the dominant motion.",
                "citations": [{
                    "url": "https://news.example/northwind-series-b",
                    "snippet": "closed a $40M Series B led by Acme Ventures",
                    "source_type": "news",
                }],
            },
            {
                "text": "Frame the commercial around RETENTION (managed onboarding + named CSM) — neutralizes the public review chorus on support latency.",
                "priority": 1,
                "timeframe": "30 days",
                "owners": ["gtm", "security"],
                "rationale": "G2 chatter on support response + onboarding is the loudest reputational signal; turning that into the offer's centerpiece is asymmetric.",
                "citations": [{
                    "url": "https://reviews.example/northwind",
                    "snippet": "report slow support response times",
                    "source_type": "review",
                }],
            },
            {
                "text": "Pre-emptively route the procurement-grade DPA / subprocessor pack so the security review doesn't stall the Q.",
                "priority": 2,
                "timeframe": "30 days",
                "owners": ["security", "finance"],
                "rationale": "DPA + SOC 2 + ISO 27001 alignment is in flight on their side; matching it removes a common deal-killer.",
                "citations": [{
                    "url": "https://news.example/northwind-soc2",
                    "snippet": "preparing a DPA update for GDPR alignment",
                    "source_type": "news",
                }],
            },
            {
                "text": "Build a head-to-head deck vs Tableau (time-to-insight) and Looker (per-seat economics) — meet them where they already position publicly.",
                "priority": 2,
                "timeframe": "this quarter",
                "owners": ["gtm"],
                "rationale": "They already wrote the comparative narrative themselves; matching their framing shortens the eval cycle.",
                "citations": [{
                    "url": "https://northwind.example/blog/why-us-vs-tableau",
                    "snippet": "outperform Tableau on time-to-first-insight by 3x",
                    "source_type": "site",
                }],
            },
            {
                "text": "Price floor to $250/seat-equivalent ARR — anchor on the enterprise tier they just published, don't discount Pro-tier comparables.",
                "priority": 3,
                "timeframe": "this quarter",
                "owners": ["finance", "gtm"],
                "rationale": "They have already taught the market that procurement-grade features cost $250/seat — pricing below that signals lower tier in evaluation.",
                "citations": [{
                    "url": "https://northwind.example/pricing",
                    "snippet": "Enterprise tier adds SSO, SCIM, and a 99.9% SLA at $250 per seat",
                    "source_type": "pricing",
                }],
            },
        ],
        "open_questions": [
            "Confirm the named exec sponsor for the EU expansion (likely a new CRO or VP Sales EU).",
            "Pull recent Stripe/Twilio/Snowflake incident histories — gauge subprocessor-chain exposure ahead of the security review.",
            "Verify whether the channel motion is partner-resale or co-sell — changes the timing on direct outreach.",
            "Quantify the support-latency complaint volume — is it 5 reviewers or 50?",
        ],
    })


# ─── Contradictions (V7.23) ───────────────────────────────────────────────

def fake_contradictions_llm(_prompt: str) -> str:
    """Canned Contradiction list aligned with the Northwind fixture claims.

    References the claim texts produced by fake_finance_llm + fake_security_llm
    above so the contradictions agent can attach citations from the parent
    claims and the test asserts the full round-trip.
    """
    return json.dumps({
        "contradictions": [
            {
                "axis": "pricing",
                "claim_a": "Northwind raised Pro tier from $49 to $79/seat — 61% increase landing alongside the new enterprise SKU.",
                "claim_b": "Public reviews flag billing surprises that contradict the new pricing-page transparency.",
                "severity": 2,
                "summary": "Pricing page presents a clean $49→$79 step, but customer reviews report unexpected charges on the same plan.",
            },
        ],
    })
