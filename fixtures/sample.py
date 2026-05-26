"""Deterministic fixtures for offline (no-key) testing.

The sample bundle deliberately plants:
  - groundable snippets (so dept agents + grounding guard have real anchors),
  - PII (email + phone) for the PII redaction guard,
  - a "CONFIDENTIAL" marker for the leak/scope guard.
"""

from __future__ import annotations

from agents.schemas import SharedBundle, SourceItem, SourceType

TARGET = "Northwind Analytics"

PII_EMAIL = "jane.doe@northwind.example"
PII_PHONE = "+1 (415) 555-0137"
CONFIDENTIAL_MARKER = "CONFIDENTIAL — internal board deck, do not distribute"


def sample_bundle() -> SharedBundle:
    return SharedBundle(
        target=TARGET,
        sources=[
            SourceItem(
                source_type=SourceType.PRICING,
                url="https://northwind.example/pricing",
                text=(
                    "Northwind Analytics raised its Pro plan from $49 to $79 per "
                    "seat this quarter, and removed the free tier. Enterprise tier "
                    "adds SSO, SCIM, and a 99.9% SLA at $250 per seat."
                ),
            ),
            SourceItem(
                source_type=SourceType.JOBS,
                url="https://northwind.example/careers",
                text=(
                    "Northwind Analytics is hiring 12 enterprise account executives "
                    "and 4 solutions engineers across North America. New roles in "
                    "EU sales leadership and a VP of Channel Partnerships."
                ),
            ),
            SourceItem(
                source_type=SourceType.NEWS,
                url="https://news.example/northwind-series-b",
                text=(
                    "Northwind Analytics closed a $40M Series B led by Acme Ventures "
                    "to expand into the EU market. Funding will fund headcount in "
                    "London and Berlin and accelerate the enterprise product."
                ),
            ),
            SourceItem(
                source_type=SourceType.REVIEW,
                url="https://reviews.example/northwind",
                text=(
                    "Customers praise Northwind's dashboards but report slow support "
                    "response times since the recent pricing change. Several G2 "
                    "reviewers cite billing surprises and slower onboarding."
                ),
            ),
            # V6 fixture additions — give the depts more material to ground
            # against, in particular for competitor_moves + regulatory + vendor.
            SourceItem(
                source_type=SourceType.SITE,
                url="https://northwind.example/blog/why-us-vs-tableau",
                text=(
                    "Our dashboards outperform Tableau on time-to-first-insight by "
                    "3x, and undercut Looker on per-seat pricing by roughly 40%. "
                    "We win evaluations against ThoughtSpot on natural-language search."
                ),
            ),
            SourceItem(
                source_type=SourceType.NEWS,
                url="https://news.example/northwind-soc2",
                text=(
                    "Northwind Analytics announced SOC 2 Type II attestation and "
                    "filed for ISO 27001. The company processes customer data in "
                    "the EU and is preparing a DPA update for GDPR alignment."
                ),
            ),
            SourceItem(
                source_type=SourceType.SITE,
                url="https://northwind.example/trust/subprocessors",
                text=(
                    "Subprocessor list: AWS (hosting), Stripe (billing), Twilio "
                    "(transactional email), Snowflake (analytics warehouse). "
                    "Customer data flows include EU→US transfers under SCCs."
                ),
            ),
            SourceItem(
                source_type=SourceType.SITE,
                url="https://northwind.example/contact",
                text=(
                    f"Reach our press office at {PII_EMAIL} or call {PII_PHONE}. "
                    f"{CONFIDENTIAL_MARKER}: projected churn 14%."
                ),
            ),
        ],
    )
