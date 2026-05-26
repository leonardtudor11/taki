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
                    "seat this quarter, and removed the free tier."
                ),
            ),
            SourceItem(
                source_type=SourceType.JOBS,
                url="https://northwind.example/careers",
                text=(
                    "Northwind Analytics is hiring 12 enterprise account executives "
                    "and 4 solutions engineers across North America."
                ),
            ),
            SourceItem(
                source_type=SourceType.NEWS,
                url="https://news.example/northwind-series-b",
                text=(
                    "Northwind Analytics closed a $40M Series B led by Acme Ventures "
                    "to expand into the EU market."
                ),
            ),
            SourceItem(
                source_type=SourceType.REVIEW,
                url="https://reviews.example/northwind",
                text=(
                    "Customers praise Northwind's dashboards but report slow support "
                    "response times since the recent pricing change."
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
