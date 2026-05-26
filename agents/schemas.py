"""Taki data contract — Pydantic schemas shared across departments.

All department outputs are grounded: every Claim carries >=1 Citation that
points back into the SharedBundle the departments consumed. The orchestrator
and guardrails rely on these shapes being stable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SourceType(str, Enum):
    SERP = "serp"
    SITE = "site"
    PRICING = "pricing"
    LINKEDIN = "linkedin"
    JOBS = "jobs"
    NEWS = "news"
    REVIEW = "review"
    OTHER = "other"


class SourceItem(BaseModel):
    """One raw scraped artifact in the shared bundle."""

    source_type: SourceType
    url: str
    text: str
    fetched_at: datetime = Field(default_factory=_now)


class SharedBundle(BaseModel):
    """The Lean single-fetch store: scrape once, every department reads this."""

    target: str  # company name or domain
    fetched_at: datetime = Field(default_factory=_now)
    sources: list[SourceItem] = Field(default_factory=list)

    def texts(self) -> list[str]:
        return [s.text for s in self.sources]


class Citation(BaseModel):
    """Anchors a claim to a snippet that exists in the SharedBundle."""

    url: str
    snippet: str  # must appear in some SourceItem.text (grounding guard checks this)
    source_type: SourceType = SourceType.OTHER


class Claim(BaseModel):
    text: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


# --- Department outputs ---

class AccountBrief(BaseModel):
    """Revenue / GTM department (Track 1)."""

    target: str
    buying_signals: list[Claim] = Field(default_factory=list)
    competitor_moves: list[Claim] = Field(default_factory=list)
    hiring_signals: list[Claim] = Field(default_factory=list)
    outreach_angle: str = ""
    generated_at: datetime = Field(default_factory=_now)

    def all_claims(self) -> list[Claim]:
        return [*self.buying_signals, *self.competitor_moves, *self.hiring_signals]


class MarketSignal(BaseModel):
    """Finance / Market department (Track 2)."""

    target: str
    pricing_trend: list[Claim] = Field(default_factory=list)
    expansion_contraction: list[Claim] = Field(default_factory=list)
    web_traffic_proxy: list[Claim] = Field(default_factory=list)
    vendor_health_flags: list[Claim] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_now)

    def all_claims(self) -> list[Claim]:
        return [
            *self.pricing_trend,
            *self.expansion_contraction,
            *self.web_traffic_proxy,
            *self.vendor_health_flags,
        ]


class RiskProfile(BaseModel):
    """Security / Compliance department (Track 3)."""

    target: str
    exposure_indicators: list[Claim] = Field(default_factory=list)
    reputational_signals: list[Claim] = Field(default_factory=list)
    regulatory_signals: list[Claim] = Field(default_factory=list)
    third_party_risk: list[Claim] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_now)

    def all_claims(self) -> list[Claim]:
        return [
            *self.exposure_indicators,
            *self.reputational_signals,
            *self.regulatory_signals,
            *self.third_party_risk,
        ]


# --- Cross-department + guardrails ---

class HandoffMessage(BaseModel):
    """Explicit dept->dept communication, surfaced in the UI."""

    from_dept: str
    to_dept: str
    message: str
    refs: list[str] = Field(default_factory=list)


class SynergySignal(BaseModel):
    """A combined signal that no single department could produce alone."""

    text: str
    contributing_depts: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class GuardrailReport(BaseModel):
    pii_redactions: int = 0
    leak_flags: list[str] = Field(default_factory=list)
    ungrounded_dropped: list[str] = Field(default_factory=list)
    passed: bool = True


class CascadeBrief(BaseModel):
    """The unified deliverable every department cascades into."""

    target: str
    generated_at: datetime = Field(default_factory=_now)
    account_brief: Optional[AccountBrief] = None
    market_signal: Optional[MarketSignal] = None
    risk_profile: Optional[RiskProfile] = None
    synergy_signals: list[SynergySignal] = Field(default_factory=list)
    handoffs: list[HandoffMessage] = Field(default_factory=list)
    guardrail_report: GuardrailReport = Field(default_factory=GuardrailReport)
    executive_summary: str = ""
