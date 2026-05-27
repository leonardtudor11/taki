"""PESTLE agent (V7.26) — macro-environment factor analysis.

Six factors scored 1-5 with a tailwind/headwind/neutral direction:
  - Political:     government stance, subsidies, geopolitical risk
  - Economic:      interest rates, FX, inflation, commodity prices
  - Social:        demographics, labour market, public acceptance
  - Technological: tech maturity, disruption velocity, patents
  - Legal:         permitting, antitrust, sector regulation
  - Environmental: climate policy, ESG mandate, physical risk

Each factor's citations are pruned against the bundle (V7.21 grounding),
so paraphrased snippets get dropped. The agent is most useful when the
bundle contains T1 regulator filings + T3 newspaper-of-record sources;
its outputs degrade gracefully when the bundle is weak.
"""

from __future__ import annotations

from agents.base import build_context, parse_into
from agents.schemas import Pestle, SharedBundle
from guardrails import grounding
from services.llm import LLMFn, get_default_llm

DEPT = "pestle"


_PROMPT = """You are a strategy analyst producing a PESTLE macro-environment
analysis for TARGET, using ONLY the source bundle below. Return JSON
in this exact shape (no wrapper, no commentary):

{
  "political":     {"name":"political",     "pressure": <1-5>, "direction": "tailwind|headwind|neutral", "assessment": "...", "citations": [{"url":"...","snippet":"...","source_type":"..."}]},
  "economic":      {"name":"economic",      "pressure": <1-5>, "direction": "...", "assessment": "...", "citations": [...]},
  "social":        {"name":"social",        "pressure": <1-5>, "direction": "...", "assessment": "...", "citations": [...]},
  "technological": {"name":"technological", "pressure": <1-5>, "direction": "...", "assessment": "...", "citations": [...]},
  "legal":         {"name":"legal",         "pressure": <1-5>, "direction": "...", "assessment": "...", "citations": [...]},
  "environmental": {"name":"environmental", "pressure": <1-5>, "direction": "...", "assessment": "...", "citations": [...]}
}

Scoring rules:
  - `pressure`: 1=barely material, 5=major macro force materially shaping
    TARGET's near-term trajectory.
  - `direction`:
      "tailwind"  = macro force helps TARGET (e.g. subsidies favoring its sector)
      "headwind"  = macro force hurts TARGET (e.g. rising interest rates eroding deal size)
      "neutral"   = material but ambiguous / could swing either way
  - `assessment`: 2-3 sentences. Concrete, specific. Avoid marketing fluff.
  - Each citation `snippet` MUST be VERBATIM from a source below. Paraphrased
    snippets get dropped after parsing.
  - If the bundle contains no signal for a factor, score pressure=1, direction="neutral",
    assessment="No specific signal in the bundle for this factor.", citations=[].
    Do not invent.

TARGET: {target}

SOURCE BUNDLE:
{bundle}
"""


def analyze(
    target: str,
    bundle: SharedBundle,
    llm: LLMFn | None = None,
) -> Pestle:
    """Return a Pestle. LLM failure / parse failure → empty Pestle (default
    PestleFactor instances)."""
    llm = llm or get_default_llm()
    prompt = (
        _PROMPT
        .replace("{target}", target)
        .replace("{bundle}", build_context(bundle))
    )
    try:
        raw = llm(prompt)
    except Exception:
        return Pestle()

    try:
        p = parse_into(raw, Pestle)
    except Exception:
        return Pestle()

    # V7.21 cite-level grounding per factor
    haystacks = [grounding._norm(t) for t in bundle.texts()]
    for fname in ("political", "economic", "social", "technological", "legal", "environmental"):
        factor = getattr(p, fname, None)
        if factor is None:
            continue
        kept = [c for c in factor.citations if grounding._cite_is_grounded(c, haystacks)]
        if len(kept) != len(factor.citations):
            setattr(p, fname, factor.model_copy(update={"citations": kept}))
    return p
