"""Porter's Five Forces agent (V7.24).

Reads the SharedBundle (the same scraped sources the dept agents see) and
produces a FiveForces analysis: each of the five competitive pressures
gets an intensity score 1-5 plus a 2-3 sentence assessment grounded in
bundle citations.

Citations are pruned with the same V7.21 cite-level grounding pass after
parsing, so anything the LLM paraphrases gets dropped.
"""

from __future__ import annotations

from agents.base import build_context, parse_into
from agents.schemas import FiveForces, SharedBundle
from guardrails import grounding
from services.llm import LLMFn, get_default_llm

DEPT = "porter"


_PROMPT = """You are a competitive strategy analyst applying Porter's Five Forces
to TARGET, using ONLY the source bundle below. Score each force 1-5
where 1 = very low pressure, 5 = very high pressure.

Return JSON in this exact shape (no wrapping object, no commentary):

{
  "rivalry":        {"name": "industry rivalry",        "intensity": <1-5>, "assessment": "...", "citations": [{"url": "...", "snippet": "...", "source_type": "..."}]},
  "new_entrants":   {"name": "threat of new entrants",  "intensity": <1-5>, "assessment": "...", "citations": [...]},
  "supplier_power": {"name": "supplier power",          "intensity": <1-5>, "assessment": "...", "citations": [...]},
  "buyer_power":    {"name": "buyer power",             "intensity": <1-5>, "assessment": "...", "citations": [...]},
  "substitutes":    {"name": "threat of substitutes",   "intensity": <1-5>, "assessment": "...", "citations": [...]}
}

Rules:
  - Every `assessment` must be 2-3 sentences, concrete, no marketing fluff.
  - Every citation `snippet` MUST be a VERBATIM copy from a source below.
    Citations whose snippet is paraphrased will be dropped after parsing.
  - `intensity` is your scoring; ground it in the cited evidence.
  - Reflect what the bundle actually shows — pricing pages, hiring pages,
    customer reviews, and external commentary all carry signal.

TARGET: {target}

SOURCE BUNDLE:
{bundle}
"""


def analyze(
    target: str,
    bundle: SharedBundle,
    llm: LLMFn | None = None,
) -> FiveForces:
    """Return a FiveForces (5 grounded Force objects). On parse failure or
    LLM error returns an empty FiveForces — the cascade still assembles."""
    llm = llm or get_default_llm()
    prompt = (
        _PROMPT
        .replace("{target}", target)
        .replace("{bundle}", build_context(bundle))
    )
    try:
        raw = llm(prompt)
    except Exception:
        return FiveForces()

    try:
        five = parse_into(raw, FiveForces)
    except Exception:
        return FiveForces()

    # V7.21 cite-level pruning per force
    haystacks = [grounding._norm(t) for t in bundle.texts()]
    for fname in ("rivalry", "new_entrants", "supplier_power", "buyer_power", "substitutes"):
        force = getattr(five, fname, None)
        if force is None:
            continue
        kept = [c for c in force.citations if grounding._cite_is_grounded(c, haystacks)]
        if len(kept) != len(force.citations):
            setattr(five, fname, force.model_copy(update={"citations": kept}))
    return five
