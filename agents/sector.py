"""V7.29 — sector-conditional sub-pipeline.

After cross_pollinate + profile_extract, the cascade routes to ONE of
four sector branches based on business_profile.industry. Each branch
runs a single LLM call that extracts sector-specific structured data:

  PHARMA   → clinical pipeline + regulatory submissions + named partners
  SAAS     → pricing tiers + PLG metrics + reference logos
  ENERGY   → installed sites + certifications + grid connections
  GENERIC  → competitive moat + operating cadence  (fallback)

Each agent is a single LLM call producing a full SectorSignal subclass.
Failures fall back to the empty signal — never break the cascade.
"""

from __future__ import annotations

import json

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agents.base import strip_fences
from agents.schemas import (
    BusinessProfile,
    EnergySignal,
    GenericSignal,
    PharmaSignal,
    SaasSignal,
    Sector,
    SectorSignal,
    SharedBundle,
    SourceSubject,
    classify_sector,
)
from services.llm import LLMFn, get_default_llm

DEPT = "sector"


def _evidence_block(bundle: SharedBundle, per_source_chars: int = 1600,
                    max_sources: int = 10) -> str:
    """Compact textual rendering of the bundle — target-owned sources first."""
    target_srcs = [s for s in (bundle.sources or [])
                   if s.subject == SourceSubject.TARGET]
    external = [s for s in (bundle.sources or [])
                if s.subject != SourceSubject.TARGET]
    ordered = (target_srcs + external)[:max_sources]
    blocks: list[str] = []
    for src in ordered:
        body = (src.text or "")[:per_source_chars]
        tag = src.source_type.value if hasattr(src.source_type, "value") else str(src.source_type)
        blocks.append(f"### [{tag}] {src.url}\n{body}")
    return "\n\n".join(blocks) if blocks else "(no evidence)"


# ──────────────────────────────────────────────────────────────────────
# Sector prompts — each is single LLM call returning the full signal.
# ──────────────────────────────────────────────────────────────────────

_PHARMA_PROMPT = """You read scraped public-web evidence about a pharma /
biopharmaceutical / life-sciences company and extract three sector-specific
intelligence buckets. JSON only.

TARGET: "{target}"
INDUSTRY: "{industry}"

EVIDENCE:
{evidence}

Return JSON with three keys, each a list (use empty list if the evidence
doesn't support the bucket — don't invent):

- pipeline: list of {{
    "name":              drug brand or development name (e.g. "HYMPAVZI", "PF-07321332"),
    "phase":             "Phase I" | "Phase II" | "Phase III" | "Approved" | "Filed",
    "indication":        the therapeutic area (e.g. "Hemophilia B", "COVID-19", "Crohn's disease"),
    "recent_milestone":  most recent public event you can cite,
    "citations":         [{{"url": "...", "snippet": "verbatim snippet from evidence"}}]
  }}

- submissions: list of {{
    "agency":            "FDA" | "EMA" | "PMDA" | "MHRA" | "Health Canada" | ...,
    "product":           drug name the submission is for,
    "submission_type":   "NDA" | "BLA" | "IND" | "510(k)" | "IDE" | "PMA" | "MAA" | ...,
    "status":            "under review" | "approved" | "filed" | "supplemental" | ...,
    "decision_window":   PDUFA or expected decision date,
    "citations":         [...]
  }}

- partners: list of {{
    "name":              named clinical / commercial partner institution or company,
    "role":              "CRO" | "academic site" | "co-developer" | "licensor" | "manufacturer" | ...,
    "program":           which drug or indication ties the partner in,
    "citations":         [...]
  }}

HARD RULES:
- Every entry MUST cite a verbatim snippet that exists in the evidence above.
  Do not paraphrase the snippet field.
- Skip entries you can't cite. Empty lists are fine.
- Output JSON only, no prose.
"""


_SAAS_PROMPT = """You read scraped public-web evidence about a SaaS / BaaS /
PaaS / dev-tools / cloud company and extract three sector-specific buckets.
JSON only.

TARGET: "{target}"
INDUSTRY: "{industry}"

EVIDENCE:
{evidence}

Return JSON with three keys, each a list (use empty list if evidence doesn't
support — don't invent):

- tiers: list of pricing-page entries {{
    "name":                    "Free" | "Pro" | "Team" | "Business" | "Enterprise" | tier name as branded,
    "price":                   raw price text (e.g. "$20/user/mo", "Custom", "Contact sales", "Free"),
    "audience":                who this tier targets ("individual developers", "SMB teams", "Fortune 500"),
    "distinguishing_feature":  what unlocks at this tier vs the one below,
    "citations":               [...]
  }}

- plg_metrics: list of product-led-growth signals {{
    "metric":       what's being counted ("monthly signups", "free→paid conversion", "WAU", "GitHub stars"),
    "value":        the value as cited ("100M+", "$5B valuation", "10k+ stars"),
    "source_quote": the verbatim phrase from the evidence,
    "citations":    [...]
  }}

- reference_logos: list of named customers / case studies {{
    "customer_name":     a named customer (not "leading retailer" — the actual name),
    "industry":          their industry,
    "deployment_scale":  "global rollout" | "5k seats" | "EU only" | etc.,
    "use_case":          what they use the product for,
    "citations":         [...]
  }}

HARD RULES:
- Every entry MUST cite a verbatim snippet from the evidence above.
- Skip entries you can't cite. Empty lists are fine.
- Output JSON only, no prose.
"""


_ENERGY_PROMPT = """You read scraped public-web evidence about an energy /
renewables / utility / heavy-infrastructure / manufacturing company and
extract three sector-specific buckets. JSON only.

TARGET: "{target}"
INDUSTRY: "{industry}"

EVIDENCE:
{evidence}

Return JSON with three keys, each a list:

- sites: list of installed / operating / commissioned sites {{
    "location":           site name + region (e.g. "Neusiedl wind farm, Austria"),
    "capacity_mw":        raw capacity text (e.g. "84 MW", "1.2 GW", "300 MWh storage"),
    "status":             "operating" | "commissioning" | "planned" | "under construction" | "decommissioned",
    "commissioning_year": year as cited,
    "citations":          [...]
  }}

- certifications: list of regulatory / standards / safety certifications {{
    "standard":  "IEC 61400-1" | "ISO 14001" | "GL guideline" | "ATEX" | "FAA Part 25" | sector standard name,
    "status":    "held" | "in progress" | "lapsed" | "applying",
    "year":      as cited,
    "citations": [...]
  }}

- grid_deals: list of grid connections / utility partnerships / off-take agreements {{
    "utility":   named transmission/distribution operator (e.g. "Transelectrica", "National Grid"),
    "region":    geography of the deal,
    "capacity":  MW / MWh in the agreement,
    "deal_type": "PPA" | "EPC" | "interconnection agreement" | "joint venture" | etc.,
    "citations": [...]
  }}

HARD RULES:
- Every entry MUST cite a verbatim snippet from the evidence above.
- Skip entries you can't cite. Empty lists are fine.
- Output JSON only.
"""


_GENERIC_PROMPT = """You read scraped public-web evidence about a company in
an industry that doesn't fit a specialised sector pipeline. Extract two
fallback signal buckets. JSON only.

TARGET: "{target}"
INDUSTRY: "{industry}"

EVIDENCE:
{evidence}

Return JSON with two keys, each a list:

- moats: list of competitive moats {{
    "axis":       what dimension they win on (e.g. "distribution network", "regulatory licence", "brand loyalty"),
    "evidence":   the supporting signal from the bundle,
    "durability": "low" | "medium" | "high",
    "citations":  [...]
  }}

- cadence: list of operating cadence signals {{
    "activity_type": "product launches" | "hiring" | "partnership announcements" | "press" | "M&A",
    "frequency":     "quarterly" | "monthly" | "weekly" | "ad-hoc",
    "most_recent":   most recent instance you can cite,
    "citations":     [...]
  }}

HARD RULES:
- Every entry MUST cite a verbatim snippet from the evidence above.
- Skip entries you can't cite.
- Output JSON only.
"""


_SECTOR_PROMPT_MAP: dict[Sector, tuple[str, type]] = {
    Sector.PHARMA:  (_PHARMA_PROMPT,  PharmaSignal),
    Sector.SAAS:    (_SAAS_PROMPT,    SaasSignal),
    Sector.ENERGY:  (_ENERGY_PROMPT,  EnergySignal),
    Sector.GENERIC: (_GENERIC_PROMPT, GenericSignal),
}


def _coerce_citations(data, bundle: SharedBundle) -> object:
    """Walk a dict/list tree and coerce bare-string citation entries to the
    Citation dict shape Pydantic expects.

    LLMs frequently emit citations as a list of plain strings (the verbatim
    snippet) rather than {url, snippet, source_type} dicts. Without coercion,
    Pydantic validation rejects the whole sector signal — we end up with an
    empty fallback. This walker recurses through any 'citations' keys and
    rewrites string entries; when possible it also resolves the source URL
    by finding the snippet inside one of the bundle's source texts.
    """
    # Build a snippet→url lookup once, lazy on first need
    source_index: list[tuple[str, str, str]] = []  # (norm_text, url, source_type)

    def _index():
        if source_index:
            return source_index
        for src in (bundle.sources or []):
            text = (src.text or "").lower()
            st = src.source_type.value if hasattr(src.source_type, "value") else str(src.source_type)
            source_index.append((text, src.url, st))
        return source_index

    def _lookup(snippet: str) -> tuple[str, str]:
        """Find first source whose text contains a slice of the snippet."""
        if not snippet:
            return ("", "site")
        needle = snippet.strip().lower()
        if len(needle) < 20:
            return ("", "site")
        # match the first 60 chars to dodge minor paraphrase
        probe = needle[:60]
        for txt, url, st in _index():
            if probe in txt:
                return (url, st)
        return ("", "site")

    def _walk(node):
        if isinstance(node, dict):
            for k, v in list(node.items()):
                if k == "citations" and isinstance(v, list):
                    coerced = []
                    for c in v:
                        if isinstance(c, dict):
                            coerced.append(c)
                        elif isinstance(c, str):
                            url, st = _lookup(c)
                            coerced.append({"url": url, "snippet": c, "source_type": st})
                        else:
                            coerced.append(c)
                    node[k] = coerced
                else:
                    _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)
        return node

    return _walk(data)


def analyze(
    bundle: SharedBundle,
    profile: BusinessProfile | None,
    sector: Sector | None = None,
    llm: LLMFn | None = None,
) -> tuple[Sector, SectorSignal]:
    """Run the sector-conditional analysis.

    If `sector` is not supplied, derive it from profile.industry via
    classify_sector(). One LLM call. Returns (sector, signal) — caller
    writes the signal into the correct CascadeBrief slot.
    """
    if sector is None:
        industry = profile.industry if profile else ""
        sector = classify_sector(industry)

    prompt_tmpl, model_cls = _SECTOR_PROMPT_MAP[sector]
    industry_str = (profile.industry if profile else "") or "(unknown)"
    empty_signal: SectorSignal = model_cls()

    if not bundle.sources:
        return (sector, empty_signal)

    llm = llm or get_default_llm()
    prompt = prompt_tmpl.format(
        target=bundle.target,
        industry=industry_str,
        evidence=_evidence_block(bundle),
    )

    # V7.29-pt2 — Vertex 429 mid-cascade is common when 6 parallel reasoning
    # agents fire LLM calls simultaneously after profile_extract. Retry the
    # sector call w/ exponential backoff so it doesn't silently fall back to
    # an empty signal just because the dept agents got the quota slot first.
    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _call() -> str:
        return llm(prompt)

    try:
        raw = _call()
        data = json.loads(strip_fences(raw))
        # coerce LLM-emitted bare-string citations to Citation dict shape so
        # Pydantic validates. Also resolves source_type+url via bundle text
        # lookup when possible.
        data = _coerce_citations(data, bundle)
        signal = model_cls.model_validate(data)
        return (sector, signal)
    except Exception:
        return (sector, empty_signal)
