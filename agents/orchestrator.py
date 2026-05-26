"""Cascade orchestrator — the 'company'.

Runs the three departments on one shared bundle (Lean: scrape once), lets their
outputs cross-pollinate (synergy + handoffs), applies the Security/Compliance
guardrails, and assembles the unified CascadeBrief.

LLMs are injected per department so the whole cascade is testable offline.
"""

from __future__ import annotations

from agents import finance, gtm, security
from agents.schemas import (
    AccountBrief,
    CascadeBrief,
    Citation,
    Claim,
    HandoffMessage,
    MarketSignal,
    RiskProfile,
    SharedBundle,
    SynergySignal,
)
from services.llm import LLMFn


class DeptOutputs:
    def __init__(
        self,
        account_brief: AccountBrief,
        market_signal: MarketSignal,
        risk_profile: RiskProfile,
    ):
        self.account_brief = account_brief
        self.market_signal = market_signal
        self.risk_profile = risk_profile


def run_departments(
    bundle: SharedBundle,
    gtm_llm: LLMFn | None = None,
    finance_llm: LLMFn | None = None,
    security_llm: LLMFn | None = None,
) -> DeptOutputs:
    """Cascade one objective into the three departments, collect their outputs."""
    return DeptOutputs(
        account_brief=gtm.analyze(bundle, llm=gtm_llm),
        market_signal=finance.analyze(bundle, llm=finance_llm),
        risk_profile=security.analyze(bundle, llm=security_llm),
    )


def _citations_of(*claim_lists: list[Claim]) -> list[Citation]:
    cites: list[Citation] = []
    for claims in claim_lists:
        if claims and claims[0].citations:
            cites.append(claims[0].citations[0])
    return cites


def _urls_of(claims: list[Claim]) -> list[str]:
    return [c.url for cl in claims for c in cl.citations]


def cross_pollinate(
    out: DeptOutputs,
) -> tuple[list[SynergySignal], list[HandoffMessage]]:
    """Derive cross-department synergy signals and explicit handoff messages.

    Deterministic: a synergy fires only when >=2 departments each contribute a
    real, cited signal — mirroring how decisions need agreement across teams.
    """
    ab, ms, rp = out.account_brief, out.market_signal, out.risk_profile
    synergies: list[SynergySignal] = []
    handoffs: list[HandoffMessage] = []

    # Finance -> GTM: pricing moves change outreach timing
    if ms.pricing_trend:
        handoffs.append(
            HandoffMessage(
                from_dept="finance",
                to_dept="gtm",
                message="Pricing change detected — adjust outreach timing/messaging.",
                refs=_urls_of(ms.pricing_trend),
            )
        )
    # Security -> GTM: reputational signals become responsible talking points
    if rp.reputational_signals:
        handoffs.append(
            HandoffMessage(
                from_dept="security",
                to_dept="gtm",
                message="Reputational signal — frame responsibly, do not weaponize.",
                refs=_urls_of(rp.reputational_signals),
            )
        )
    # GTM -> Security: hiring expands the attack/vendor surface
    if ab.hiring_signals:
        handoffs.append(
            HandoffMessage(
                from_dept="gtm",
                to_dept="security",
                message="Hiring expansion — new attack surface / vendors to monitor.",
                refs=_urls_of(ab.hiring_signals),
            )
        )

    # Synergy: price increase + reputational complaints => churn-risk timing
    if ms.pricing_trend and rp.reputational_signals:
        synergies.append(
            SynergySignal(
                text=(
                    "Pricing increase coincides with support/reputation complaints "
                    "— churn risk; time GTM outreach around retention, not upsell."
                ),
                contributing_depts=["finance", "security"],
                citations=_citations_of(ms.pricing_trend, rp.reputational_signals),
            )
        )
    # Synergy: hiring + expansion/funding => growth account, prioritize
    if ab.hiring_signals and (ms.expansion_contraction or ab.buying_signals):
        synergies.append(
            SynergySignal(
                text=(
                    "Hiring plus funding/expansion signals a growth account — "
                    "prioritize and resource the outreach."
                ),
                contributing_depts=["gtm", "finance"],
                citations=_citations_of(
                    ab.hiring_signals, ms.expansion_contraction or ab.buying_signals
                ),
            )
        )

    return synergies, handoffs
