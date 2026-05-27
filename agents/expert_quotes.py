"""V7.34 — Expert-quote extractor.

Scans the shared bundle for verbatim quotes attributed to named
individuals — founders, executives, regulators, industry analysts,
academic researchers, named journalists. Returns up to N ExpertQuote
records, each with the verbatim text + a citation URL.

One LLM call per cascade. Failures fall back to an empty list — never
breaks the cascade. Runs in target-mode AND self-mode (founders quoting
analysts about their own market is valuable too).
"""

from __future__ import annotations

import json

from agents.base import strip_fences
from agents.profile import _evidence_block
from agents.schemas import ExpertQuote, SharedBundle
from services.llm import LLMFn, get_default_llm

DEPT = "expert_quotes"

# Hard cap so a chatty LLM can't blow up the brief. Each quote shipped to
# the dashboard takes ~80-180 chars; 12 quotes ≈ 1.5-2.5KB. Comfortable
# for a panel above departments without overwhelming the layout.
MAX_QUOTES = 12

_PROMPT = """You are reading scraped public-web evidence about "{target}".
Extract VERBATIM quotes attributed to NAMED individuals — and ONLY
verbatim quotes that appear inside quotation marks (or are clearly
attributed via phrases like "said X" / "according to X").

EVIDENCE:
{evidence}

Return JSON ONLY (no prose, no markdown fences) with this shape:
{{
  "quotes": [
    {{
      "name": "Albert Bourla",
      "role": "CEO",
      "organization": "Pfizer",
      "quote": "We expect to file BLA submissions for two oncology programs in 2025.",
      "citation": "https://investors.pfizer.com/..."
    }},
    ...
  ]
}}

Rules:
  - quote: VERBATIM text only, max 280 chars. If a quote runs longer,
    pick the most decision-relevant single sentence.
  - name: the individual's name. Skip the entry if you cannot attribute.
  - role: their job title at quote time ("CEO", "Senior Analyst",
    "Principal Investigator", "Reporter"). Empty string if unstated.
  - organization: the firm / institution. Empty string if independent.
  - citation: the URL the quote came from (use the [tag] URL from
    the evidence block). Empty string if you cannot trace it.
  - Prefer quotes from EXTERNAL voices (analysts, regulators,
    journalists, researchers) over the target's own marketing copy —
    quotes from the target's own CEO are still valuable, but rank them
    after third-party voices.
  - Skip generic platitudes ("we're committed to excellence"). Each
    quote must carry a SPECIFIC fact, forecast, or position.
  - Return at most {max_quotes} entries. Fewer is fine; an empty list
    is fine if the evidence really has no attributable quotes.

Output JSON only."""


def analyze(bundle: SharedBundle, llm: LLMFn | None = None) -> list[ExpertQuote]:
    """Extract expert quotes from the bundle. One LLM call.

    Returns a list of ExpertQuote (possibly empty). Never raises —
    parsing or LLM failures degrade to []. The caller (cascade_graph)
    stuffs the result into brief.expert_quotes.
    """
    if not bundle or not bundle.sources:
        return []

    llm = llm or get_default_llm()
    prompt = _PROMPT.format(
        target=bundle.target,
        evidence=_evidence_block(bundle),
        max_quotes=MAX_QUOTES,
    )
    try:
        raw = llm(prompt)
        obj = json.loads(strip_fences(raw))
    except Exception:
        return []

    # Tolerate both {"quotes": [...]} and a bare [...] response shape.
    items = obj.get("quotes") if isinstance(obj, dict) else obj
    if not isinstance(items, list):
        return []

    out: list[ExpertQuote] = []
    seen_quotes: set[str] = set()  # dedupe by verbatim text
    for entry in items[: MAX_QUOTES * 2]:  # over-fetch then filter
        if not isinstance(entry, dict):
            continue
        try:
            q = ExpertQuote.model_validate(entry)
        except Exception:
            continue
        # Skip entries with empty quote text — the verbatim quote is the
        # whole point; a name+role with no quote carries no information.
        if not (q.quote or "").strip():
            continue
        key = q.quote.strip().lower()
        if key in seen_quotes:
            continue
        seen_quotes.add(key)
        # Clamp quote length to the prompt cap as a safety net (an LLM
        # that ignores the 280-char instruction shouldn't pollute the
        # dashboard layout).
        if len(q.quote) > 320:
            q.quote = q.quote[:317].rstrip() + "..."
        out.append(q)
        if len(out) >= MAX_QUOTES:
            break
    return out
