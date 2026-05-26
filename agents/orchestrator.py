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
    MarketSignal,
    RiskProfile,
    SharedBundle,
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
