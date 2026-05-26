"""Taki data contract — Pydantic schemas shared across departments.

All department outputs are grounded: every Claim carries >=1 Citation that
points back into the SharedBundle the departments consumed. The orchestrator
and guardrails rely on these shapes being stable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


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


class SourceSubject(str, Enum):
    """Who this source is about. Lets self-mode prompts distinguish 'your
    own site' from a competitor's site so analysis stays grounded in the
    right perspective."""

    TARGET = "target"          # target-account intelligence (default)
    SELF = "self"              # the user's own business
    COMPETITOR = "competitor"  # a named competitor of the user's business


class SourceItem(BaseModel):
    """One raw scraped artifact in the shared bundle."""

    source_type: SourceType
    url: str
    text: str
    subject: SourceSubject = SourceSubject.TARGET
    competitor_name: str = ""  # populated when subject == COMPETITOR
    fetched_at: datetime = Field(default_factory=_now)


class SharedBundle(BaseModel):
    """The Lean single-fetch store: scrape once, every department reads this."""

    target: str  # company name or domain
    fetched_at: datetime = Field(default_factory=_now)
    sources: list[SourceItem] = Field(default_factory=list)

    def texts(self) -> list[str]:
        return [s.text for s in self.sources]

    def texts_by_subject(self, subject: SourceSubject) -> list[str]:
        return [s.text for s in self.sources if s.subject == subject]

    def competitor_names(self) -> list[str]:
        seen: list[str] = []
        for s in self.sources:
            if s.subject == SourceSubject.COMPETITOR and s.competitor_name \
                    and s.competitor_name not in seen:
                seen.append(s.competitor_name)
        return seen


class Citation(BaseModel):
    """Anchors a claim to a snippet that exists in the SharedBundle."""

    url: str
    snippet: str  # must appear in some SourceItem.text (grounding guard checks this)
    source_type: SourceType = SourceType.OTHER

    @field_validator("source_type", mode="before")
    @classmethod
    def _coerce_source_type(cls, v):
        """LLMs invent labels like 'live_web' or 'company_page'. Fall back to OTHER."""
        if v is None:
            return SourceType.OTHER
        if isinstance(v, SourceType):
            return v
        if isinstance(v, str):
            s = v.strip().lower()
            for st in SourceType:
                if st.value == s:
                    return st
            return SourceType.OTHER
        return SourceType.OTHER


_CONFIDENCE_WORDS = {
    "very high": 0.95, "high": 0.85, "medium high": 0.7, "med high": 0.7,
    "medium": 0.5, "med": 0.5, "moderate": 0.5,
    "medium low": 0.3, "med low": 0.3, "low": 0.25, "very low": 0.1, "none": 0.0,
}


class Claim(BaseModel):
    text: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v):
        """LLMs love returning 'high'/'medium'/'low' or percent strings. Coerce."""
        if v is None:
            return 0.5
        if isinstance(v, (int, float)):
            f = float(v)
            if f > 1.0:  # treat 0-100 as percent for consistency w/ string branch
                f /= 100.0
            return max(0.0, min(1.0, f))
        if isinstance(v, str):
            s = v.strip().lower().rstrip("%")
            if s in _CONFIDENCE_WORDS:
                return _CONFIDENCE_WORDS[s]
            try:
                f = float(s)
                # treat 0-100 as percent
                if f > 1.0:
                    f /= 100.0
                return max(0.0, min(1.0, f))
            except ValueError:
                return 0.5
        return 0.5


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


class MarketingSignal(BaseModel):
    """Marketing department (V7) — positioning, brand voice, content + channel.

    In self-mode the user's site is analysed for what *they* should improve.
    In target-mode the same shape captures the target's marketing posture.
    """

    target: str
    value_proposition: list[Claim] = Field(default_factory=list)
    positioning: list[Claim] = Field(default_factory=list)
    brand_voice: list[Claim] = Field(default_factory=list)
    content_gaps: list[Claim] = Field(default_factory=list)
    channel_signals: list[Claim] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_now)

    def all_claims(self) -> list[Claim]:
        return [
            *self.value_proposition,
            *self.positioning,
            *self.brand_voice,
            *self.content_gaps,
            *self.channel_signals,
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


class CascadeMode(str, Enum):
    """What perspective the cascade is run from.

    - target: classic — analyze an enterprise account someone else might sell to.
    - self:   V7 — small business analyses ITSELF + its competitors. Strategy
              produces a plan FOR the user, not about them.
    """

    TARGET = "target"
    SELF = "self"


class Stage(str, Enum):
    """Business maturity stage — used by the strategy prompt to tune advice."""

    IDEA = "idea"
    MVP = "mvp"
    PRE_REVENUE = "pre-revenue"
    EARLY_REVENUE = "early-revenue"
    GROWTH = "growth"
    SCALE = "scale"


class BusinessProfile(BaseModel):
    """User-supplied context for self-mode cascades.

    Captured from the onboarding form on the dashboard so the strategy agent
    has the founder's intent (goals, stage, ICP) — analysis without intent
    devolves into generic SWOT.
    """

    name: str
    url: str
    industry: str = ""
    stage: Stage = Stage.EARLY_REVENUE
    goal: str = ""
    customer_segment: str = ""
    competitor_urls: list[str] = Field(default_factory=list)
    competitor_names: list[str] = Field(default_factory=list)

    @field_validator("stage", mode="before")
    @classmethod
    def _coerce_stage(cls, v):
        if isinstance(v, Stage):
            return v
        if isinstance(v, str):
            s = v.strip().lower().replace("_", "-")
            for tier in Stage:
                if tier.value == s:
                    return tier
        return Stage.EARLY_REVENUE


class FitTier(str, Enum):
    """Coarse ICP fit ranking — high/medium/low only, so output stays decision-ready."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class StrategicPlay(BaseModel):
    """One prioritized action — what to do, why, when, who owns it."""

    text: str
    priority: int = Field(default=3, ge=1, le=5)   # 1 = urgent, 5 = later
    timeframe: str = ""                            # "30 days" / "this quarter" / etc.
    owners: list[str] = Field(default_factory=list)  # depts that own this play
    rationale: str = ""
    citations: list[Citation] = Field(default_factory=list)

    @field_validator("priority", mode="before")
    @classmethod
    def _coerce_priority(cls, v):
        """LLMs return 'urgent', 'P1', '1', etc. Coerce to int 1..5."""
        if isinstance(v, int):
            return max(1, min(5, v))
        if isinstance(v, str):
            s = v.strip().lower().lstrip("p")
            words = {"urgent": 1, "high": 2, "medium": 3, "med": 3, "low": 4, "later": 5}
            if s in words:
                return words[s]
            try:
                return max(1, min(5, int(float(s))))
            except ValueError:
                return 3
        return 3


class StrategicPlan(BaseModel):
    """Strategy department output — the synthesized 'so what' for the target.

    Built after grounding + cross-pollination so it can quote claims from any
    of the three departments. The dashboard renders this hero-style above the
    evidence panels: headline + narrative + ICP/deal-size/urgency stat grid +
    prioritized plays + open questions.
    """

    target: str
    headline: str = ""                             # one-sentence sharpest framing
    narrative: str = ""                            # 2-3 paragraph exec summary
    icp_fit: FitTier = FitTier.MEDIUM
    icp_rationale: str = ""
    deal_size_estimate: str = ""                   # "$50k-$200k ARR" or similar
    deal_size_rationale: str = ""
    urgency: str = ""                              # "act this quarter" / "monitor"
    urgency_rationale: str = ""
    recommended_plays: list[StrategicPlay] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_now)

    @field_validator("icp_fit", mode="before")
    @classmethod
    def _coerce_fit(cls, v):
        if v is None:
            return FitTier.MEDIUM
        if isinstance(v, FitTier):
            return v
        if isinstance(v, str):
            s = v.strip().lower()
            for tier in FitTier:
                if tier.value == s:
                    return tier
        return FitTier.MEDIUM


class CascadeBrief(BaseModel):
    """The unified deliverable every department cascades into."""

    target: str
    mode: CascadeMode = CascadeMode.TARGET
    business_profile: Optional[BusinessProfile] = None  # populated in self-mode
    generated_at: datetime = Field(default_factory=_now)
    account_brief: Optional[AccountBrief] = None
    market_signal: Optional[MarketSignal] = None
    marketing_signal: Optional[MarketingSignal] = None
    risk_profile: Optional[RiskProfile] = None
    synergy_signals: list[SynergySignal] = Field(default_factory=list)
    handoffs: list[HandoffMessage] = Field(default_factory=list)
    guardrail_report: GuardrailReport = Field(default_factory=GuardrailReport)
    executive_summary: str = ""
    strategic_plan: Optional[StrategicPlan] = None
