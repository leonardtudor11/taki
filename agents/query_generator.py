"""V7.36 — Dynamic LLM-driven SERP query generator.

The hardcoded _industry_template_for() in services/brightdata.py covers
a few known industries (wind energy, backend-as-a-service, branded
pharmaceuticals, SaaS knowledge tools). Any NEW industry — cybersecurity,
EV charging, vertical AI, hospitality tech, climate fintech — falls
through to the V7.28 generic fallback (Trustpilot, Glassdoor, outage,
lawsuit, funding, layoff, leadership). That's broad coverage but it
misses the SPECIFICITY a sector-savvy researcher would ask for: an
EV-charging company's brief needs UL certification + grid-interconnect
+ federal NEVI funding queries; a vertical-AI company needs HuggingFace
+ benchmark leaderboard + safety policy queries.

This module produces an industry-tailored query bank in one LLM call.
Output merges with the existing default_external_queries layers.

Failure mode: on any error, returns [] and the caller proceeds with
the existing layered query bank — never breaks cascade.

Cache: results memoized in-process by (industry, region, stage) so
repeated cascades against the same sector don't re-LLM the query
plan. Cache lives for the server process lifetime.
"""

from __future__ import annotations

import json

from agents.base import strip_fences
from agents.schemas import SourceType
from services.llm import LLMFn, get_default_llm

DEPT = "query_generator"
MAX_QUERIES_DEFAULT = 8

# (industry_lower, region_lower, stage_lower) -> list[(query, SourceType)]
_QUERY_CACHE: dict[tuple[str, str, str], list[tuple[str, SourceType]]] = {}

_PROMPT = """You are a senior research analyst designing a Google SERP query
bank to investigate "{target}" — a {stage_phrase} company in the
"{industry}" industry{region_phrase}.

Your job: emit up to {max_queries} highly tailored Google queries that
surface the kinds of public web sources that meaningfully de-risk an
investment / partnership / competitive assessment for THIS specific
industry. Skip generic queries like "{target} reviews" (those already
run); focus on industry-defining surfaces.

For each query, pick a source_type label from this enum (lowercase):
  - news    : news / analyst / regulatory filing / earnings
  - review  : community / aggregator / forum (Reddit, HN, G2)
  - pricing : pricing page / plans / pricing comparison
  - jobs    : careers / hiring intel
  - site    : the target's own site / sub-page
  - linkedin: LinkedIn pulse / profile / company page
  - other   : academic / podcast / technical doc / standards body

OUTPUT JSON ONLY:
{{
  "queries": [
    {{"query": "\\"{target}\\" UL Listed inverter certification 2024", "source_type": "news"}},
    {{"query": "\\"{target}\\" NEVI award OR federal funding", "source_type": "news"}},
    ...
  ]
}}

Rules:
  - Each query MUST be specific to the "{industry}" industry. Generic
    queries waste budget.
  - Use site: operators to lock specific high-signal domains where
    they exist for this industry (e.g. site:fda.gov for pharma,
    site:sec.gov for filings, site:rfc-editor.org for networking,
    site:ahima.org for health-IT). Include 2-4 site-locked queries.
  - Use filetype:pdf when the industry's signal lives in PDFs
    (whitepapers, technical specs, annual reports).
  - Use date qualifiers (after:2024-01-01) on queries about
    fast-moving topics (funding, recent launches, regulatory
    decisions).
  - Wrap the target name in quotes for exact-match.
  - Keep each query under 180 chars.

Output JSON only — no prose, no markdown fences."""


def _build_prompt(target: str, industry: str, region: str, stage: str,
                   max_queries: int) -> str:
    stage_phrase = (stage or "").strip() or "growth-stage"
    region_phrase = f" headquartered in {region}" if region else ""
    return _PROMPT.format(
        target=target,
        industry=industry,
        stage_phrase=stage_phrase,
        region_phrase=region_phrase,
        max_queries=max_queries,
    )


def generate_queries(
    target: str,
    industry: str,
    region: str = "",
    stage: str = "",
    llm: LLMFn | None = None,
    max_queries: int = MAX_QUERIES_DEFAULT,
) -> list[tuple[str, SourceType]]:
    """LLM-generated SERP queries tuned to the industry/stage/region.

    Returns [] when industry is empty or LLM fails — caller falls back
    to the static query layers.
    """
    if not (industry or "").strip():
        return []

    llm = llm or get_default_llm()
    prompt = _build_prompt(target, industry, region, stage, max_queries)
    try:
        raw = llm(prompt)
        obj = json.loads(strip_fences(raw))
    except Exception:
        return []

    items = obj.get("queries") if isinstance(obj, dict) else obj
    if not isinstance(items, list):
        return []

    out: list[tuple[str, SourceType]] = []
    seen: set[str] = set()
    for entry in items[: max_queries * 2]:
        if not isinstance(entry, dict):
            continue
        q = (entry.get("query") or "").strip()
        if not q or len(q) > 200:
            continue
        # dedupe identical queries
        norm = q.lower()
        if norm in seen:
            continue
        seen.add(norm)
        kind_raw = (entry.get("source_type") or "news").strip().lower()
        try:
            st = SourceType(kind_raw)
        except Exception:
            st = SourceType.OTHER
        out.append((q, st))
        if len(out) >= max_queries:
            break
    return out


def generate_queries_cached(
    target: str,
    industry: str,
    region: str = "",
    stage: str = "",
    llm: LLMFn | None = None,
    max_queries: int = MAX_QUERIES_DEFAULT,
) -> list[tuple[str, SourceType]]:
    """generate_queries with per-(target, industry, region, stage) memo.

    Target is included in the key so cached queries (which have the
    target name already substituted in by the LLM) don't leak between
    cascades. Same target re-run (e.g. via scripts/rerun_briefs.py)
    hits the cache and skips the LLM call.

    Different target in the same industry pays the full LLM cost. We
    don't try to template-substitute cached queries cross-target
    because the LLM may place the target name in unpredictable
    positions (inside quoted strings, qualifiers, etc.).
    """
    key = (
        (industry or "").lower().strip(),
        (region   or "").lower().strip(),
        (stage    or "").lower().strip(),
        (target   or "").lower().strip(),
    )
    cached = _QUERY_CACHE.get(key)
    if cached is not None:
        return cached
    out = generate_queries(
        target=target, industry=industry, region=region, stage=stage,
        llm=llm, max_queries=max_queries,
    )
    _QUERY_CACHE[key] = out
    return out


def clear_cache() -> None:
    """Test helper — drop the in-process query cache."""
    _QUERY_CACHE.clear()
