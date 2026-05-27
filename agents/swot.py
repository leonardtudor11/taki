"""SWOT agent (V7.24).

Classic SWOT 2×2 against the SharedBundle. Each cell is a list of
SwotItem entries, each item carrying a 1-2 sentence text plus citation-
grounded evidence from the bundle.

Internal vs external axis:
  - Strengths     — internal positives the target can lean on
  - Weaknesses    — internal gaps the target carries
  - Opportunities — external openings in the market
  - Threats       — external pressures that could erode the position
"""

from __future__ import annotations

from agents.base import build_context, parse_into
from agents.schemas import SharedBundle, Swot
from guardrails import grounding
from services.llm import LLMFn, get_default_llm

DEPT = "swot"


_PROMPT = """You are a strategy analyst producing a SWOT analysis for TARGET
from the source bundle below. Return JSON in this exact shape (no wrapper,
no commentary):

{
  "strengths":     [{"text": "...", "impact": <1-3>, "citations": [{"url":"...","snippet":"...","source_type":"..."}]}],
  "weaknesses":    [{"text": "...", "impact": <1-3>, "citations": [...]}],
  "opportunities": [{"text": "...", "impact": <1-3>, "citations": [...]}],
  "threats":       [{"text": "...", "impact": <1-3>, "citations": [...]}]
}

Rules:
  - 2-5 items per quadrant (don't pad — quality over quantity).
  - Each `text` is 1-2 concrete sentences. Avoid marketing words ("innovative",
    "world-class") unless the bundle uses them and you cite that usage.
  - `impact`: 1=minor, 2=moderate, 3=material to the strategic picture.
  - Every citation `snippet` MUST be VERBATIM from a source below. Paraphrased
    snippets are dropped after parsing.
  - Strengths/weaknesses = internal (about the target itself).
    Opportunities/threats = external (market/competitor/regulatory pressures).

TARGET: {target}

SOURCE BUNDLE:
{bundle}
"""


def _prune_items(items, haystacks):
    """Return new list w/ each item's citations pruned to verified-only.
    Items whose cites are completely empty after pruning are still kept —
    their text may still be a synthesis of bundle evidence — but they render
    without any evidence chips."""
    out = []
    for it in items:
        kept = [c for c in it.citations if grounding._cite_is_grounded(c, haystacks)]
        if len(kept) != len(it.citations):
            out.append(it.model_copy(update={"citations": kept}))
        else:
            out.append(it)
    return out


def analyze(
    target: str,
    bundle: SharedBundle,
    llm: LLMFn | None = None,
) -> Swot:
    """Return a Swot. Failures leave empty quadrants — the cascade doesn't
    block on framework agents."""
    llm = llm or get_default_llm()
    prompt = (
        _PROMPT
        .replace("{target}", target)
        .replace("{bundle}", build_context(bundle))
    )
    try:
        raw = llm(prompt)
    except Exception:
        return Swot()

    try:
        swot = parse_into(raw, Swot)
    except Exception:
        return Swot()

    haystacks = [grounding._norm(t) for t in bundle.texts()]
    return swot.model_copy(update={
        "strengths":     _prune_items(swot.strengths,     haystacks),
        "weaknesses":    _prune_items(swot.weaknesses,    haystacks),
        "opportunities": _prune_items(swot.opportunities, haystacks),
        "threats":       _prune_items(swot.threats,       haystacks),
    })
