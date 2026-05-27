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


# ─── Porter's Five Forces (V7.24) ─────────────────────────────────────────

def fake_porter_llm(_prompt: str) -> str:
    """Canned FiveForces aligned w/ the Northwind sample bundle. All
    citation snippets are copied verbatim from fixtures.sample.sample_bundle."""
    return json.dumps({
        "rivalry": {
            "name": "industry rivalry",
            "intensity": 4,
            "assessment": "Northwind is fighting an established analytics incumbent with a public comparison page; the new $250/seat enterprise tier is a head-on bid for the same procurement-led deals competitors anchor on.",
            "citations": [{
                "url": "https://northwind.example/blog/why-us-vs-tableau",
                "snippet": "outperform Tableau on time-to-first-insight by 3x",
                "source_type": "site",
            }],
        },
        "new_entrants": {
            "name": "threat of new entrants",
            "intensity": 2,
            "assessment": "Procurement-grade requirements (SSO, SCIM, SOC 2, ISO) raise the floor for new entrants; Northwind cleared SOC 2 Type II and has ISO 27001 filed, locking in a meaningful barrier.",
            "citations": [{
                "url": "https://news.example/northwind-soc2",
                "snippet": "SOC 2 Type II cleared, ISO 27001 filed",
                "source_type": "news",
            }],
        },
        "supplier_power": {
            "name": "supplier power",
            "intensity": 3,
            "assessment": "Northwind's subprocessor stack (AWS, Stripe, Twilio, Snowflake) gives moderate concentration risk — each vendor outage cascades, and Snowflake pricing pressure flows directly through their COGS.",
            "citations": [{
                "url": "https://northwind.example/trust/subprocessors",
                "snippet": "AWS (us-east-1, eu-west-1), Stripe, Twilio, Snowflake",
                "source_type": "site",
            }],
        },
        "buyer_power": {
            "name": "buyer power",
            "intensity": 3,
            "assessment": "Enterprise customers with seats-based pricing have moderate power — the new $79 Pro and $250 enterprise tiers signal Northwind is testing the ceiling; public reviews flagging billing surprises show pushback is starting.",
            "citations": [{
                "url": "https://reviews.example/northwind",
                "snippet": "billing surprises and a slow first onboarding",
                "source_type": "review",
            }],
        },
        "substitutes": {
            "name": "threat of substitutes",
            "intensity": 3,
            "assessment": "Tableau remains the obvious substitute and Northwind acknowledges it head-on in their own marketing comparison; commoditisation of dashboards via free/open-source tools is a slower-moving but real pressure.",
            "citations": [{
                "url": "https://northwind.example/blog/why-us-vs-tableau",
                "snippet": "outperform Tableau on time-to-first-insight by 3x",
                "source_type": "site",
            }],
        },
    })


# ─── SWOT (V7.24) ─────────────────────────────────────────────────────────

def fake_swot_llm(_prompt: str) -> str:
    """Canned SWOT aligned w/ the Northwind sample bundle."""
    return json.dumps({
        "strengths": [
            {
                "text": "Funded growth runway from a fresh Series B with a clear EU mandate.",
                "impact": 3,
                "citations": [{
                    "url": "https://news.example/northwind-series-b",
                    "snippet": "closed a $40M Series B led by Acme Ventures",
                    "source_type": "news",
                }],
            },
            {
                "text": "Procurement-ready security posture: SOC 2 Type II cleared and ISO 27001 in progress.",
                "impact": 3,
                "citations": [{
                    "url": "https://news.example/northwind-soc2",
                    "snippet": "SOC 2 Type II cleared, ISO 27001 filed",
                    "source_type": "news",
                }],
            },
        ],
        "weaknesses": [
            {
                "text": "Public reviews flag billing surprises and slow first-month onboarding — friction at the procurement-to-go-live handoff.",
                "impact": 2,
                "citations": [{
                    "url": "https://reviews.example/northwind",
                    "snippet": "billing surprises and a slow first onboarding",
                    "source_type": "review",
                }],
            },
        ],
        "opportunities": [
            {
                "text": "Enterprise SKU with SSO/SCIM/99.9% SLA opens up a procurement-led upper tier the existing Pro plan couldn't address.",
                "impact": 3,
                "citations": [{
                    "url": "https://northwind.example/pricing",
                    "snippet": "Enterprise tier adds SSO, SCIM, and a 99.9% SLA at $250 per seat",
                    "source_type": "pricing",
                }],
            },
        ],
        "threats": [
            {
                "text": "Tableau remains a direct head-to-head; the public comparison page concedes that buyers actively evaluate both.",
                "impact": 2,
                "citations": [{
                    "url": "https://northwind.example/blog/why-us-vs-tableau",
                    "snippet": "outperform Tableau on time-to-first-insight by 3x",
                    "source_type": "site",
                }],
            },
        ],
    })


# ─── PESTLE (V7.26) ───────────────────────────────────────────────────────

def fake_pestle_llm(_prompt: str) -> str:
    """Canned PESTLE aligned w/ the Northwind sample bundle. Citations are
    verbatim from the fixture's source texts."""
    return json.dumps({
        "political": {
            "name": "political",
            "pressure": 2,
            "direction": "neutral",
            "assessment": "No explicit political signal in the bundle for Northwind; the Series B was a private round with no regulatory disclosure beyond standard.",
            "citations": [],
        },
        "economic": {
            "name": "economic",
            "pressure": 4,
            "direction": "tailwind",
            "assessment": "Fresh $40M Series B capitalization provides 18-24 month runway; the new $250/seat enterprise tier suggests pricing power has expanded into procurement-led deal sizes.",
            "citations": [{
                "url": "https://news.example/northwind-series-b",
                "snippet": "closed a $40M Series B led by Acme Ventures",
                "source_type": "news",
            }],
        },
        "social": {
            "name": "social",
            "pressure": 2,
            "direction": "neutral",
            "assessment": "Public reviews flag onboarding friction and billing transparency — moderate social signal but not yet a reputational drag.",
            "citations": [{
                "url": "https://reviews.example/northwind",
                "snippet": "billing surprises and a slow first onboarding",
                "source_type": "review",
            }],
        },
        "technological": {
            "name": "technological",
            "pressure": 3,
            "direction": "neutral",
            "assessment": "Tableau remains a direct technological substitute; Northwind's claimed 3x time-to-insight advantage is the public framing of that competition.",
            "citations": [{
                "url": "https://northwind.example/blog/why-us-vs-tableau",
                "snippet": "outperform Tableau on time-to-first-insight by 3x",
                "source_type": "site",
            }],
        },
        "legal": {
            "name": "legal",
            "pressure": 3,
            "direction": "tailwind",
            "assessment": "SOC 2 Type II already cleared and ISO 27001 filed — procurement-grade compliance now in hand, which is itself a legal/regulatory tailwind for enterprise sales.",
            "citations": [{
                "url": "https://news.example/northwind-soc2",
                "snippet": "SOC 2 Type II cleared, ISO 27001 filed",
                "source_type": "news",
            }],
        },
        "environmental": {
            "name": "environmental",
            "pressure": 1,
            "direction": "neutral",
            "assessment": "Northwind operates a cloud analytics platform; no direct environmental exposure visible in the bundle.",
            "citations": [],
        },
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


# ─── Expert Quotes (V7.34) ───────────────────────────────────────────────

def fake_expert_quotes_llm(_prompt: str) -> str:
    """Canned ExpertQuote list shaped for the Northwind fixture.

    Three quotes spanning the value strata the V7.34 panel ranks:
      1) external analyst commentary (Gartner-style framing)
      2) external journalist coverage (Reuters-style attributable fact)
      3) target's own CEO — kept LAST because the schema/agent ranks
         third-party voices first per the prompt.
    """
    return json.dumps({
        "quotes": [
            {
                "name": "Lakshmi Patel",
                "role": "Principal Analyst",
                "organization": "Gartner",
                "quote": "Northwind's pivot toward enterprise SKUs is forcing the mid-market SaaS pricing reset everyone in this space saw coming.",
                "citation": "https://gartner.example/report",
            },
            {
                "name": "Mark Reynolds",
                "role": "Reporter",
                "organization": "Reuters",
                "quote": "Northwind raised its Pro tier from $49 to $79 per seat in March, citing demand for the new enterprise compliance bundle.",
                "citation": "https://www.reuters.com/example",
            },
            {
                "name": "Priya Sharma",
                "role": "CEO",
                "organization": "Northwind Analytics",
                "quote": "We're investing every dollar of the new pricing into the security and compliance roadmap our enterprise customers asked for.",
                "citation": "https://northwind.example/blog",
            },
        ],
    })


# ─── Cross-pollinate (V7.35) ─────────────────────────────────────────────

def fake_cross_pollinate_llm(_prompt: str) -> str:
    """Canned LLM cross-pollinate output for the Northwind fixture.

    Returns 2 personalized handoffs + 1 personalized synergy that
    reference Northwind-specific facts (the $49→$79 pricing move, the
    enterprise SKU launch) — distinct from the deterministic templates
    so tests can assert the LLM path won.

    URLs picked from the Northwind sample bundle so the refs filter in
    cross_pollinate_llm.analyze() preserves them.
    """
    return json.dumps({
        "handoffs": [
            {
                "from_dept": "finance",
                "to_dept": "gtm",
                "message": "Northwind raised Pro from $49 to $79/seat alongside the enterprise SKU — outbound sequencing should lead with the new enterprise bundle, not the legacy Pro plan.",
                "refs": ["https://northwind.example/pricing"],
            },
            {
                "from_dept": "security",
                "to_dept": "gtm",
                "message": "Northwind's SOC2 Type II + new enterprise compliance bundle is the talking point that opens enterprise doors — pair every outbound sequence with the compliance evidence.",
                "refs": ["https://northwind.example/security"],
            },
        ],
        "synergies": [
            {
                "text": "Northwind's $49→$79 Pro price hike LANDING alongside a new enterprise compliance bundle = explicit market-segmentation play, not opportunistic pricing — GTM should reframe outbound around the enterprise tier rather than discount the Pro plan.",
                "contributing_depts": ["finance", "security"],
                "citations": [
                    {"url": "https://northwind.example/pricing", "snippet": "Pro tier $79", "source_type": "pricing"},
                    {"url": "https://northwind.example/security", "snippet": "SOC2", "source_type": "site"},
                ],
            },
        ],
    })


def fake_cross_pollinate_llm_empty(_prompt: str) -> str:
    """Empty-shape response — triggers the templated fallback branch."""
    return json.dumps({"handoffs": [], "synergies": []})
