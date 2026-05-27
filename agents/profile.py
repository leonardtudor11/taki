"""V7.28 — Business profile extractor for target-mode cascades.

Self-mode receives a BusinessProfile from the founder onboarding form.
Target-mode has no profile — until V7.27, brief.business_profile ended up
null, which blanked the corresponding dashboard section and starved the
strategy prompt of industry/stage context.

This agent runs ONLY in target-mode, BEFORE strategy. One LLM call against
the cleaned bundle. Failures fall back to (name, url) only — the cascade
never breaks on profile extraction.
"""

from __future__ import annotations

import json

from agents.base import strip_fences
from agents.schemas import (
    BusinessProfile,
    SharedBundle,
    SourceSubject,
    SourceType,
    Stage,
)
from services.llm import LLMFn, get_default_llm

DEPT = "profile"

_PROMPT = """You read scraped public-web evidence about a company and extract
its business profile. Return JSON ONLY — no prose, no markdown fences.

TARGET: "{target}"
PRIMARY URL: {url}

EVIDENCE (target's own sources first, then external coverage):
{evidence}

Return JSON with these fields, ALL required:
- name: company name as the evidence brands it
- url: primary URL (string above, or the first target-owned URL in evidence)
- industry: short specific noun phrase. Be specific — "tech" / "software" are
  too generic. Good: "BaaS / Postgres database platform", "wind turbine
  manufacturing & installation", "branded prescription pharmaceuticals",
  "SaaS workplace productivity / knowledge tools".
- stage: one of "idea", "mvp", "pre-revenue", "early-revenue", "growth", "scale".
  Use the evidence:
    - "scale" = mature enterprise (>$1B revenue OR >5000 employees OR public
      large-cap; e.g. Fortune 500, big pharma, hyperscalers)
    - "growth" = scaling rapidly, recent funding rounds, hiring spike,
      $10M-$1B revenue range
    - "early-revenue" = paying customers but small (<$10M revenue, <100 emp)
    - "pre-revenue" = product live, no customers yet
    - "mvp" = prototype only
    - "idea" = no product
- goal: 1-sentence inferred current strategic priority. Examples:
  "expand into enterprise AI offerings", "complete IPO under SEC S-1 review",
  "achieve FDA approval for [drug]", "scale wind farm portfolio in
  Eastern Europe", "convert PLG users to enterprise contracts".
- customer_segment: who they sell to. Be specific. Examples:
  "DevOps teams at mid-market SaaS companies (50-500 engineers)",
  "EU utility-scale wind farm operators (>50MW)",
  "global pharma sales organizations + their CROs",
  "knowledge-worker teams at SMB and mid-market".
- competitor_names: 0-5 NAMED competitors mentioned in the evidence.
  NOT generic categories like "other SaaS tools". Skip if the evidence
  doesn't name any.

Output JSON only."""


def _evidence_block(bundle: SharedBundle, per_source_chars: int = 1800,
                    max_sources: int = 10) -> str:
    """Compact textual rendering of the bundle for prompt consumption.

    Prioritises target-owned sources first (subject=TARGET), then external
    coverage. Caps each source to ~1800 chars + 10 sources total to keep
    the prompt under ~20k tokens.
    """
    target_sources = [s for s in (bundle.sources or [])
                       if s.subject == SourceSubject.TARGET]
    external = [s for s in (bundle.sources or [])
                if s.subject != SourceSubject.TARGET]
    ordered = (target_sources + external)[:max_sources]
    blocks: list[str] = []
    for src in ordered:
        body = (src.text or "")[:per_source_chars]
        tag = src.source_type.value if hasattr(src.source_type, "value") else str(src.source_type)
        blocks.append(f"### [{tag}] {src.url}\n{body}")
    return "\n\n".join(blocks) if blocks else "(no evidence in bundle)"


def _primary_url(bundle: SharedBundle) -> str:
    """First target-owned SITE source, else first source of any kind."""
    for src in (bundle.sources or []):
        if (src.subject == SourceSubject.TARGET
                and src.source_type == SourceType.SITE
                and src.url):
            return src.url
    for src in (bundle.sources or []):
        if src.url:
            return src.url
    return ""


def analyze(bundle: SharedBundle, llm: LLMFn | None = None) -> BusinessProfile:
    """Extract a BusinessProfile from a scraped bundle. One LLM call.

    Returns a minimal fallback (target name + primary url) on any error so
    the cascade never breaks on profile extraction.
    """
    target = bundle.target
    primary = _primary_url(bundle)
    fallback = BusinessProfile(
        name=target,
        url=primary,
        # populate known competitors from the bundle's competitor sources
        competitor_names=bundle.competitor_names(),
    )

    if not bundle.sources:
        return fallback

    llm = llm or get_default_llm()
    prompt = _PROMPT.format(
        target=target,
        url=primary or "(unknown)",
        evidence=_evidence_block(bundle),
    )
    try:
        raw = llm(prompt)
        data = json.loads(strip_fences(raw))
        # always preserve target name + URL (LLM may emit shortened versions)
        data.setdefault("name", target)
        data.setdefault("url", primary)
        # union LLM-emitted competitor names with any subject=COMPETITOR
        # sources in the bundle (which are ground truth)
        llm_competitors = data.get("competitor_names") or []
        bundle_competitors = bundle.competitor_names()
        merged: list[str] = []
        for n in (bundle_competitors + llm_competitors):
            if n and n not in merged:
                merged.append(n)
        data["competitor_names"] = merged[:8]
        return BusinessProfile.model_validate(data)
    except Exception:
        return fallback
