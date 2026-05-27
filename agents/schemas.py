"""Taki data contract — Pydantic schemas shared across departments.

All department outputs are grounded: every Claim carries >=1 Citation that
points back into the SharedBundle the departments consumed. The orchestrator
and guardrails rely on these shapes being stable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _AutoListBase(BaseModel):
    """Tolerates a common LLM mistake: returning a single dict / string for a
    field declared as a list, instead of a 1-element list. Without this the
    real-LLM Marketing / Strategy paths blow up on minor JSON-shape drift
    (the user hit this with a real Orchid SRL self-mode run: every
    MarketingSignal field came back as one dict instead of `[{...}]`).

    Coercion rules (run BEFORE Pydantic field validation):
      - field declared list[...] AND value is None → []
      - field declared list[...] AND value is dict → [dict]
      - field declared list[...] AND value is str  → [str]
      - everything else passes through unchanged.

    Inheriting from this instead of BaseModel directly opts a schema in.
    """

    @model_validator(mode="before")
    @classmethod
    def _wrap_singletons(cls, data):
        if not isinstance(data, dict):
            return data
        for name, field in cls.model_fields.items():
            if name not in data:
                continue
            ann_str = str(field.annotation)
            if "list[" not in ann_str and "List[" not in ann_str:
                continue
            v = data[name]
            if v is None:
                data[name] = []
            elif isinstance(v, dict):
                data[name] = [v]
            elif isinstance(v, str):
                # only safe for list[str] fields; for list[Claim] this will
                # fail validation downstream with a clear 'expected dict for
                # Claim' message rather than the cryptic 'expected list'.
                data[name] = [v]
        return data


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


class SourceItem(_AutoListBase):
    """One raw scraped artifact in the shared bundle."""

    source_type: SourceType
    url: str
    text: str
    subject: SourceSubject = SourceSubject.TARGET
    competitor_name: str = ""  # populated when subject == COMPETITOR
    fetched_at: datetime = Field(default_factory=_now)


class SharedBundle(_AutoListBase):
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


class Citation(_AutoListBase):
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


class Claim(_AutoListBase):
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

class AccountBrief(_AutoListBase):
    """Revenue / GTM department (Track 1)."""

    target: str
    buying_signals: list[Claim] = Field(default_factory=list)
    competitor_moves: list[Claim] = Field(default_factory=list)
    hiring_signals: list[Claim] = Field(default_factory=list)
    outreach_angle: str = ""
    generated_at: datetime = Field(default_factory=_now)

    def all_claims(self) -> list[Claim]:
        return [*self.buying_signals, *self.competitor_moves, *self.hiring_signals]


class MarketSignal(_AutoListBase):
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


class MarketingSignal(_AutoListBase):
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


class RiskProfile(_AutoListBase):
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

class HandoffMessage(_AutoListBase):
    """Explicit dept->dept communication, surfaced in the UI."""

    from_dept: str
    to_dept: str
    message: str
    refs: list[str] = Field(default_factory=list)


class SynergySignal(_AutoListBase):
    """A combined signal that no single department could produce alone."""

    text: str
    contributing_depts: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class GuardrailReport(_AutoListBase):
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


class BusinessProfile(_AutoListBase):
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


class StrategicPlay(_AutoListBase):
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


class StrategicPlan(_AutoListBase):
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


class PestleFactor(_AutoListBase):
    """V7.26 — one of the six PESTLE macro factors, scored against the bundle.

    `pressure`: 1=neutral / barely material, 5=major macro force.
    `direction`: "tailwind" (helps target), "headwind" (hurts target),
                 "neutral" (material but ambiguous).
    """

    name: str = ""
    pressure: int = Field(default=3, ge=1, le=5)
    direction: str = "neutral"                     # tailwind / headwind / neutral
    assessment: str = ""
    citations: list[Citation] = Field(default_factory=list)

    @field_validator("pressure", mode="before")
    @classmethod
    def _coerce_pressure(cls, v):
        if isinstance(v, int):
            return max(1, min(5, v))
        if isinstance(v, str):
            s = v.strip().lower()
            words = {"very low": 1, "low": 2, "moderate": 3, "medium": 3, "high": 4, "very high": 5, "extreme": 5}
            if s in words:
                return words[s]
            try:
                return max(1, min(5, int(float(s))))
            except ValueError:
                return 3
        return 3

    @field_validator("direction", mode="before")
    @classmethod
    def _coerce_direction(cls, v):
        if v is None:
            return "neutral"
        s = str(v).strip().lower()
        if s in ("up", "positive", "tailwind", "+", "favorable", "favourable", "supportive"):
            return "tailwind"
        if s in ("down", "negative", "headwind", "-", "adverse", "unfavorable", "unfavourable"):
            return "headwind"
        if s in ("tailwind", "headwind", "neutral"):
            return s
        return "neutral"


class Pestle(_AutoListBase):
    """V7.26 — PESTLE macro-environment analysis.

    Six factors: Political, Economic, Social, Technological, Legal,
    Environmental. Each one carries a citation-grounded assessment of how
    the outside world is currently affecting (or about to affect) the
    target. Renders as a 2×3 grid with direction arrows + intensity bars.
    """

    political:     PestleFactor = Field(default_factory=lambda: PestleFactor(name="political"))
    economic:      PestleFactor = Field(default_factory=lambda: PestleFactor(name="economic"))
    social:        PestleFactor = Field(default_factory=lambda: PestleFactor(name="social"))
    technological: PestleFactor = Field(default_factory=lambda: PestleFactor(name="technological"))
    legal:         PestleFactor = Field(default_factory=lambda: PestleFactor(name="legal"))
    environmental: PestleFactor = Field(default_factory=lambda: PestleFactor(name="environmental"))


class Force(_AutoListBase):
    """V7.24 — one of Porter's Five Forces, scored against the bundle."""

    name: str = ""                                  # 'industry rivalry', 'new entrants', etc.
    intensity: int = Field(default=3, ge=1, le=5)   # 1=very low pressure, 5=very high
    assessment: str = ""                            # 2-3 sentence analytical narrative
    citations: list[Citation] = Field(default_factory=list)

    @field_validator("intensity", mode="before")
    @classmethod
    def _coerce_intensity(cls, v):
        if isinstance(v, int):
            return max(1, min(5, v))
        if isinstance(v, str):
            s = v.strip().lower()
            words = {
                "very low": 1, "low": 2, "moderate": 3, "medium": 3, "med": 3,
                "high": 4, "very high": 5, "extreme": 5,
            }
            if s in words:
                return words[s]
            try:
                return max(1, min(5, int(float(s))))
            except ValueError:
                return 3
        return 3


class FiveForces(_AutoListBase):
    """V7.24 — Porter's Five Forces analysis. Snapshot of the competitive
    pressures the target faces, scored 1-5 on each force.

    Each Force.assessment must be grounded in bundle text (verbatim citation
    snippets, same rule as dept claims). The radar/pentagon view in the
    frontend reads `intensity` per force; the cards underneath surface the
    `assessment` text + citations.
    """

    rivalry:        Force = Field(default_factory=lambda: Force(name="industry rivalry"))
    new_entrants:   Force = Field(default_factory=lambda: Force(name="threat of new entrants"))
    supplier_power: Force = Field(default_factory=lambda: Force(name="supplier power"))
    buyer_power:    Force = Field(default_factory=lambda: Force(name="buyer power"))
    substitutes:    Force = Field(default_factory=lambda: Force(name="threat of substitutes"))


class SwotItem(_AutoListBase):
    """V7.24 — one cell of the SWOT 2×2."""

    text: str = ""
    citations: list[Citation] = Field(default_factory=list)
    impact: int = Field(default=2, ge=1, le=3)      # 1=minor, 3=material

    @field_validator("impact", mode="before")
    @classmethod
    def _coerce_impact(cls, v):
        if isinstance(v, int):
            return max(1, min(3, v))
        if isinstance(v, str):
            s = v.strip().lower()
            words = {"minor": 1, "low": 1, "moderate": 2, "medium": 2, "med": 2, "major": 3, "high": 3, "material": 3}
            if s in words:
                return words[s]
            try:
                return max(1, min(3, int(float(s))))
            except ValueError:
                return 2
        return 2


class Swot(_AutoListBase):
    """V7.24 — classic SWOT 2×2: internal (strengths/weaknesses) vs external
    (opportunities/threats). Each cell is a small list of citation-grounded
    SwotItem entries so the reader can verify the claim."""

    strengths:     list[SwotItem] = Field(default_factory=list)
    weaknesses:    list[SwotItem] = Field(default_factory=list)
    opportunities: list[SwotItem] = Field(default_factory=list)
    threats:       list[SwotItem] = Field(default_factory=list)


class Contradiction(_AutoListBase):
    """V7.23 — two grounded claims that disagree on the same axis.

    The contradictions agent reads every surviving claim across all depts
    and surfaces pairs where the two sources are mutually inconsistent
    (uptime promises vs documented outages, marketing pricing vs scraped
    pricing, compliance breadth claims vs explicit gaps, etc.).

    Each side keeps its own citations so the reader can verify the
    tension is real, not a misread by the agent.
    """

    axis: str = ""                                  # short topic: 'uptime', 'pricing', 'compliance', 'valuation'
    claim_a: str = ""                               # surviving claim text from one source
    citations_a: list[Citation] = Field(default_factory=list)
    claim_b: str = ""                               # contradicting claim from a different source
    citations_b: list[Citation] = Field(default_factory=list)
    severity: int = Field(default=2, ge=1, le=3)    # 1=minor disagreement, 3=material conflict
    summary: str = ""                               # one-sentence framing of the tension

    @field_validator("severity", mode="before")
    @classmethod
    def _coerce_severity(cls, v):
        if isinstance(v, int):
            return max(1, min(3, v))
        if isinstance(v, str):
            s = v.strip().lower()
            words = {"minor": 1, "low": 1, "moderate": 2, "medium": 2, "med": 2, "major": 3, "high": 3, "material": 3}
            if s in words:
                return words[s]
            try:
                return max(1, min(3, int(float(s))))
            except ValueError:
                return 2
        return 2


# ════════════════════════════════════════════════════════════════════
# V7.29 — Sector-conditional sub-pipeline
#
# Different industries deserve different topology. A pharma cascade
# should surface clinical pipeline + regulatory submissions + KOL
# partnerships. A SaaS cascade should surface pricing tier + PLG
# metrics + reference logos. The 5 universal frameworks (Porter, SWOT,
# PESTLE, Contradictions, Strategy) stay sector-agnostic because that
# IS their value. But the bundle-derived signals branch by sector.
# ════════════════════════════════════════════════════════════════════


class Sector(str, Enum):
    """V7.29 — sector classification picked by the cascade router."""

    PHARMA = "pharma"
    SAAS = "saas"
    ENERGY = "energy"
    GENERIC = "generic"


# Substring → Sector mapping. The cascade router lowercases
# business_profile.industry and matches the first hit. Order matters
# (more-specific keywords before broader ones).
_SECTOR_KEYWORDS: list[tuple[str, "Sector"]] = [
    # pharma / life sciences
    ("pharmac",        Sector.PHARMA),
    ("biotech",        Sector.PHARMA),
    ("biopharm",       Sector.PHARMA),
    ("life science",   Sector.PHARMA),
    ("clinical",       Sector.PHARMA),
    ("therapeutic",    Sector.PHARMA),
    ("drug",           Sector.PHARMA),
    ("medical device", Sector.PHARMA),
    # energy / infrastructure / manufacturing
    ("wind",           Sector.ENERGY),
    ("solar",          Sector.ENERGY),
    ("renewable",      Sector.ENERGY),
    ("energy",         Sector.ENERGY),
    ("utility",        Sector.ENERGY),
    ("grid",           Sector.ENERGY),
    ("turbine",        Sector.ENERGY),
    ("nuclear",        Sector.ENERGY),
    ("manufactur",     Sector.ENERGY),
    ("infrastructure", Sector.ENERGY),
    ("automotive",     Sector.ENERGY),
    ("aerospace",      Sector.ENERGY),
    # SaaS / cloud / developer tools
    ("saas",           Sector.SAAS),
    ("paas",           Sector.SAAS),
    ("baas",           Sector.SAAS),
    ("backend-as",     Sector.SAAS),
    ("database",       Sector.SAAS),
    ("devtool",        Sector.SAAS),
    ("developer",      Sector.SAAS),
    ("productivity",   Sector.SAAS),
    ("workspace",      Sector.SAAS),
    ("collaboration",  Sector.SAAS),
    ("knowledge",      Sector.SAAS),
    ("cloud",          Sector.SAAS),
    ("software",       Sector.SAAS),
    ("platform",       Sector.SAAS),
]


def classify_sector(industry: str | None) -> Sector:
    """Substring-match the industry string against known sector keywords.
    Falls back to GENERIC when no keyword hits (unknown / brand-new sector).
    """
    if not industry:
        return Sector.GENERIC
    s = industry.lower()
    for keyword, sector in _SECTOR_KEYWORDS:
        if keyword in s:
            return sector
    return Sector.GENERIC


# ── PHARMA branch — clinical pipeline + regulatory + partnerships ────

class DrugPipelineItem(_AutoListBase):
    """One drug / therapeutic in the target's pipeline."""

    name: str = ""
    phase: str = ""              # e.g. "Phase II", "Phase III", "Approved"
    indication: str = ""         # e.g. "Hemophilia B", "Crohn's"
    recent_milestone: str = ""   # most recent public event
    citations: list[Citation] = Field(default_factory=list)


class RegulatorySubmission(_AutoListBase):
    """One regulatory filing / submission."""

    agency: str = ""             # FDA / EMA / PMDA / ...
    product: str = ""
    submission_type: str = ""    # NDA / BLA / IND / IDE / 510(k) / etc.
    status: str = ""             # under review / approved / refused
    decision_window: str = ""    # PDUFA date or expected decision
    citations: list[Citation] = Field(default_factory=list)


class ClinicalPartner(_AutoListBase):
    """A named clinical / commercial partner."""

    name: str = ""               # institution or company
    role: str = ""               # CRO / academic site / co-developer
    program: str = ""            # which drug / indication tied to
    citations: list[Citation] = Field(default_factory=list)


class PharmaSignal(_AutoListBase):
    """V7.29 — pharma sector signal. Replaces generic plays w/ clinical depth."""

    pipeline: list[DrugPipelineItem] = Field(default_factory=list)
    submissions: list[RegulatorySubmission] = Field(default_factory=list)
    partners: list[ClinicalPartner] = Field(default_factory=list)


# ── SAAS branch — pricing tier + PLG metric + reference logo ─────────

class PricingTier(_AutoListBase):
    """One pricing tier on the target's pricing page."""

    name: str = ""               # Free / Pro / Business / Enterprise
    price: str = ""              # raw text — could be "$20/user/mo" or "Contact us"
    audience: str = ""           # who this tier targets
    distinguishing_feature: str = ""  # what unlocks at this tier
    citations: list[Citation] = Field(default_factory=list)


class PLGMetric(_AutoListBase):
    """A product-led-growth signal."""

    metric: str = ""             # signup volume / freemium ratio / WAU mention
    value: str = ""              # quote or paraphrase
    source_quote: str = ""       # the verbatim phrase from the bundle
    citations: list[Citation] = Field(default_factory=list)


class ReferenceLogo(_AutoListBase):
    """A named customer / case study."""

    customer_name: str = ""
    industry: str = ""
    deployment_scale: str = ""   # "global rollout", "10k seats", etc.
    use_case: str = ""
    citations: list[Citation] = Field(default_factory=list)


class SaasSignal(_AutoListBase):
    """V7.29 — SaaS / BaaS / dev-tools sector signal."""

    tiers: list[PricingTier] = Field(default_factory=list)
    plg_metrics: list[PLGMetric] = Field(default_factory=list)
    reference_logos: list[ReferenceLogo] = Field(default_factory=list)


# ── ENERGY branch — sites + certifications + grid connection ─────────

class InstalledSite(_AutoListBase):
    """An operating / commissioned / under-construction site."""

    location: str = ""           # site name + region
    capacity_mw: str = ""        # raw text e.g. "84 MW", "1.2 GW"
    status: str = ""             # operating / commissioning / planned
    commissioning_year: str = ""
    citations: list[Citation] = Field(default_factory=list)


class CertificationItem(_AutoListBase):
    """A standards / regulatory certification."""

    standard: str = ""           # IEC 61400-1 / ISO 14001 / GL / etc.
    status: str = ""             # held / in progress / lapsed
    year: str = ""
    citations: list[Citation] = Field(default_factory=list)


class GridConnection(_AutoListBase):
    """A grid connection or utility partnership."""

    utility: str = ""            # named transmission/distribution operator
    region: str = ""
    capacity: str = ""           # MW / MWh in agreement
    deal_type: str = ""          # PPA / EPC / interconnect agreement
    citations: list[Citation] = Field(default_factory=list)


class EnergySignal(_AutoListBase):
    """V7.29 — energy / infrastructure / manufacturing sector signal."""

    sites: list[InstalledSite] = Field(default_factory=list)
    certifications: list[CertificationItem] = Field(default_factory=list)
    grid_deals: list[GridConnection] = Field(default_factory=list)


# ── GENERIC branch — fallback for sectors w/o a specialised pipeline ─

class CompetitiveMoat(_AutoListBase):
    """An axis along which the target out-positions competitors."""

    axis: str = ""               # what dimension they win on
    evidence: str = ""           # the supporting signal
    durability: str = ""         # "low" / "medium" / "high" — how moaty
    citations: list[Citation] = Field(default_factory=list)


class OperatingCadence(_AutoListBase):
    """A cadence signal — how often they release / announce / hire."""

    activity_type: str = ""      # launches / hiring / partnerships / press
    frequency: str = ""          # quarterly / monthly / weekly / ad-hoc
    most_recent: str = ""        # most recent instance
    citations: list[Citation] = Field(default_factory=list)


class GenericSignal(_AutoListBase):
    """V7.29 — fallback sector signal for industries w/o a specialised branch."""

    moats: list[CompetitiveMoat] = Field(default_factory=list)
    cadence: list[OperatingCadence] = Field(default_factory=list)


# ── union of all sector signals ──────────────────────────────────────

SectorSignal = Union[PharmaSignal, SaasSignal, EnergySignal, GenericSignal]


class CascadeBrief(_AutoListBase):
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
    contradictions: list[Contradiction] = Field(default_factory=list)
    five_forces: Optional[FiveForces] = None
    swot: Optional[Swot] = None
    pestle: Optional[Pestle] = None
    guardrail_report: GuardrailReport = Field(default_factory=GuardrailReport)
    executive_summary: str = ""
    strategic_plan: Optional[StrategicPlan] = None
    # V7.29 — sector-conditional sub-pipeline output. Exactly one of the
    # four sector signals is populated based on business_profile.industry;
    # the others stay None.
    sector: Optional[Sector] = None
    pharma_signal: Optional[PharmaSignal] = None
    saas_signal: Optional[SaasSignal] = None
    energy_signal: Optional[EnergySignal] = None
    generic_signal: Optional[GenericSignal] = None
