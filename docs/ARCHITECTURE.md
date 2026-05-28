# Taki — Architecture

Deep technical reference. For the high-level overview + quickstart, see [`../README.md`](../README.md). For the design-decision narrative ("why did we build it this way"), see [`JOURNEY.md`](JOURNEY.md).

---

## Table of contents

1. [Data flow at a glance](#1-data-flow-at-a-glance)
2. [LangGraph state graph](#2-langgraph-state-graph)
3. [Source-tier system + SERP discovery](#3-source-tier-system--serp-discovery)
4. [The SharedBundle + guardrails](#4-the-sharedbundle--guardrails)
5. [Department agents (Tracks 1+2+3 + Marketing)](#5-department-agents)
6. [Cross-pollination](#6-cross-pollination-handoffs--synergies)
7. [Strategy + the 4 framework agents](#7-strategy--the-4-framework-agents)
8. [Grounding guard — claim level + cite level](#8-grounding-guard)
9. [Pydantic schemas + LLM-drift tolerance](#9-pydantic-schemas--llm-drift-tolerance)
10. [Frontend rendering pipeline](#10-frontend-rendering-pipeline)
11. [SSE event protocol](#11-sse-event-protocol)
12. [Testing strategy](#12-testing-strategy)
13. [Deployment topology](#13-deployment-topology)

---

## 1. Data flow at a glance

```
user input (target + URLs + industry + region)
   │
   ▼
[1] services/brightdata.discover_external_sources
   │   default_external_queries(target, industry, region)
   │      └── base (3) + industry layer (3-6) + region tokens
   │   for each query: client.unlock("https://www.google.com/search?q=...")
   │   parse_serp_results → list[str] URLs (Google internals + target host filtered out)
   │   classify_url → assign T1-T6 + drop BLOCKED
   │   apply low_tier_cap (T5+T6 ≤ 30% of bundle)
   │   → list[(url, SourceType)] external sources
   ▼
[2] services/brightdata.build_bundle
   │   for each (url, source_type) in user_urls + external:
   │       client.unlock(url) → html → html_to_text → SourceItem(text[:8000])
   │   → SharedBundle(target, sources)
   ▼
[3] agents/cascade_graph.build_graph(...).invoke({"bundle": bundle})
   │
   │   pii_redact      → strip emails + phones from every SourceItem.text
   │   leak_filter     → drop sources flagged confidential (T3 publishers exempt)
   │
   │      ┌──── gtm        agents/gtm.analyze      → AccountBrief
   │      ├──── finance    agents/finance.analyze  → MarketSignal
   │      ├──── marketing  agents/marketing.analyze → MarketingSignal
   │      └──── security   agents/security.analyze → RiskProfile
   │
   │   grounding       → guardrails/grounding.filter_claims (claim + cite level)
   │   cross_pollinate → handoffs + synergies
   │
   │      ┌──── strategy            agents/strategy.analyze       → StrategicPlan
   │      ├──── contradictions_pass agents/contradictions.analyze → list[Contradiction]
   │      ├──── porter_pass         agents/porter.analyze         → FiveForces
   │      ├──── swot_pass           agents/swot.analyze           → Swot
   │      └──── pestle_pass         agents/pestle.analyze         → Pestle
   │
   │   assemble        → pack everything into CascadeBrief
   ▼
[4] CascadeBrief written to:
       data/<slug>/brief.json    (per-target persistent cache)
       frontend/brief.json       (latest run, served by Vercel)
```

Every step that uses an LLM accepts a dependency-injected `llm: LLMFn | None`. In the production cascade these come from `services.llm.get_default_llm()` (Vertex AI Gemini 2.5 Pro). In tests they come from `fixtures/fake_llm.py`. The shape of the resulting `CascadeBrief` is byte-identical.

---

## 2. LangGraph state graph

The orchestrator is a `langgraph.StateGraph` declared in [`agents/cascade_graph.py`](../agents/cascade_graph.py). The graph is constructed inside `build_graph(...)` so all LLM callables stay closure-bound and the persisted state is JSON-serialisable.

```
                                 START
                                   ▼
                              pii_redact
                                   ▼
                              leak_filter
                                   │
        ┌────────────────┬─────────┴─────────┬────────────────┐
        ▼                ▼                   ▼                ▼
       gtm            finance            marketing         security        (parallel)
        │                │                   │                │
        └────────────────┴─────────┬─────────┴────────────────┘
                                   ▼
                                grounding
                                   ▼
                            cross_pollinate
                                   │
       ┌────────────┬─────────────┬┴─────────┬────────────────┐
       ▼            ▼             ▼          ▼                ▼
    strategy  contradictions   porter      swot            pestle          (parallel)
       _pass         _pass     _pass       _pass            _pass
       │            │             │          │                │
       └────────────┴─────────────┴──────────┴────────────────┘
                                   ▼
                                assemble
                                   ▼
                                  END
```

`CascadeState` is a `TypedDict` (see [`cascade_graph.py:CascadeState`](../agents/cascade_graph.py)) with reducer-merged fields for the parallel branches:

```python
class CascadeState(TypedDict, total=False):
    bundle: SharedBundle
    clean: SharedBundle
    pii_count: int
    leak_flags: list[str]
    account_brief: AccountBrief
    market_signal: MarketSignal
    marketing_signal: MarketingSignal
    risk_profile: RiskProfile
    dropped: Annotated[list[str], operator.add]
    synergies: list[SynergySignal]
    handoffs: list[HandoffMessage]
    strategic_plan: StrategicPlan
    contradictions: list[Contradiction]
    five_forces: FiveForces
    swot: Swot
    pestle: Pestle
    events: Annotated[list[dict], operator.add]
    brief: CascadeBrief
    business_profile: BusinessProfile
    mode: CascadeMode
```

Two annotations use `operator.add` so when the parallel branches converge into `assemble`, their accumulated `dropped` claim texts and `events` get concatenated rather than overwriting.

**Why LangGraph instead of plain async fan-out?** The state graph topology is explicit, every node is independently testable, and the per-node event callback lands directly into the SSE stream that drives the cytoscape animation in the dashboard. Sequential refactors stay one-line edits — adding `pestle_pass` was 5 lines in `build_graph` + a node function + state field.

---

## 3. Source-tier system + SERP discovery

### 3.1 The tier classifier

`services.brightdata.classify_url(url)` returns one of seven values based on hostname-suffix match against `_TIER_SUFFIXES`:

| Code | Tier | Why this tier exists | Weight |
|---|---|---|---|
| `T1_REGULATOR` | Regulator / official statistic / IGO | `*.gov`, `*.europa.eu`, `iea.org`, `irena.org`, `oecd.org`, `imf.org`, `worldbank.org`, `sec.gov`, `transelectrica.ro`, `ofgem.gov.uk`, ... | 1.00 |
| `T2_ACADEMIC` | Peer-reviewed + policy research institute | `scholar.google.com`, `nature.com`, `arxiv.org`, `pubmed`, `*.edu`, `sei.org`, `eeb.org`, `bruegel.org`, `iiasa.ac.at`, ... | 1.00 |
| `T3_NEWS` | Newspaper of record + top-tier analyst | `ft.com`, `bloomberg.com`, `reuters.com`, `wsj.com`, `economist.com`, `mckinsey.com`, `gartner.com`, `forrester.com`, ... | 0.85 |
| `T4_TRADE` | Trade publication + recognized expert column | `techcrunch.com`, `theinformation.com`, `hpcwire.com`, `redmonk.com`, `windpowermonthly.com`, `energynomics.ro`, `windeurope.org`, ... | 0.70 |
| `T5_COMMUNITY` | Community / aggregator (capped at 30% of bundle) | `reddit.com`, `news.ycombinator.com`, `medium.com`, `linkedin.com`, `quora.com`, `stackoverflow.com`, ... | 0.40 |
| `T6_REVIEW` | Review aggregator (capped with T5) | `g2.com`, `trustpilot.com`, `capterra.com`, `glassdoor.com`, ... | 0.50 |
| `T0_UNKNOWN` | No suffix match | Falls through to T4 weight | 0.60 |
| `"BLOCKED"` | Hard-drop | `blogspot.com`, `wordpress.com`, `facebook.com`, `instagram.com`, `tiktok.com`, ... | 0 |

The classifier is intentionally substring-based — it's fast, deterministic, and the trade-off (a sub-domain like `news.bloomberg.com` correctly matches `bloomberg.com`) is acceptable.

### 3.2 Industry-aware query templates

The SERP query set is derived from the target name + the `industry` field on the request payload (or `BusinessProfile.industry` in self-mode):

```python
# services/brightdata.default_external_queries
base = [
    (f'"{target}" filetype:pdf annual report OR 10-K OR prospectus',  SourceType.NEWS),
    (f'"{target}" "Financial Times" OR Reuters OR Bloomberg',         SourceType.NEWS),
    (f'"{target}" site:scholar.google.com OR site:arxiv.org OR study', SourceType.OTHER),
]

# industry layer — substring match against _INDUSTRY_QUERIES keys
# e.g. "wind energy" / "wind turbines" / "windpower" all hit the "wind" template:
"wind": [
    ('"{target}" IRENA OR "wind energy"',                        SourceType.NEWS),
    ('"{target}" "Wind Power Monthly" OR "WindEurope"',          SourceType.NEWS),
    ('"wind energy {region}" market report 2024 OR 2025',        SourceType.NEWS),
    ('"EU Green Deal" wind OR renewable 2024 OR 2025',           SourceType.NEWS),
    ('site:iea.org OR site:irena.org "wind" {region}',           SourceType.NEWS),
    ('"{target}" filetype:pdf',                                   SourceType.NEWS),
],
```

Currently shipped templates: `wind`, `solar`, `renewable`, `backend`, `database`, `saas`, `biotech`, `health`, `fintech`, `manufacturing`. Adding more is one dict entry away.

### 3.3 Region expansion

```python
_REGION_EXPAND = {
    "romania": "Romania OR EU OR Eastern Europe",
    "ro":      "Romania OR EU OR Eastern Europe",
    "uk":      "United Kingdom OR UK OR Britain",
    "us":      "United States OR US OR USA",
    "germany": "Germany OR DACH",
    "france":  "France OR EU",
    "eu":      "European Union OR EU",
}
```

A wind-energy company in Romania picks up both Romanian-specific AND Eastern-European coverage automatically.

### 3.4 The merge step + low-tier cap

`discover_external_sources` runs each query through Web Unlocker, parses the SERP HTML, classifies each candidate URL, and applies the cap:

```python
# pseudocode of services/brightdata.discover_external_sources
for query, stype in queries:
    html = client.unlock(f"https://www.google.com/search?q={quote(query)}")
    for u in parse_serp_results(html, exclude_hosts=target_hosts):
        tier = classify_url(u)
        if tier == "BLOCKED":  continue
        candidates.append((u, stype, tier))

# Cap T5+T6 share at low_tier_cap (default 0.30)
low_tier_max = max(1, int(len(candidates) * 0.30))
out = []
low_tier_kept = 0
for u, st, tier in candidates:
    if tier in (T5_COMMUNITY, T6_REVIEW):
        if low_tier_kept >= low_tier_max:
            on_event({"status": "tier_dropped", "url": u, "tier": tier, ...})
            continue
        low_tier_kept += 1
    out.append((u, st))
```

The on_event stream lets the dashboard tip strip show real-time tier classification ("`🔎 SERP tiers · T1=4 · T3=3 · T4=2 · T5=3 · kept 12`").

### 3.5 Empirical impact

Tier shares are computed across the **citations in the final brief**, not across the raw scrape — claims that get dropped by the grounding guard don't count.

| Run | Bundle | Cites | Unique cite domains | T5 community share | Top external publishers cited |
|---|---|---|---|---|---|
| Supabase pre-V7.22 (manual URLs only, no SERP) | 6 | 100 → after V7.21 prune: 86 | 1 (`supabase.com` 100%) | n/a | none |
| Supabase post-V7.22 (SERP added, no tier cap) | 18 | 105 → after V7.21 prune: 98 | 4 (`supabase.com` 75%, `reddit.com` 14%, `techcrunch.com` 9%) | 14% | TechCrunch |
| Supabase post-V7.26 (tier classifier + industry queries + low-tier cap) | 22 | 90 | 9 | 14.4% (cap is 30%) | Reuters, Bloomberg, HPCWire, futuremarketinsights, technavio |
| Orchid post-V7.26 (industry=wind, region=Romania) | 22 | 79 | 8 | 11.4% | IRENA, IEA, WindEurope, energynomics.ro, SEI, EEB |

The Reddit-monoculture problem is structurally fixed by the low-tier cap, not just statistically.

---

## 4. The SharedBundle + guardrails

### 4.1 SharedBundle

```python
class SharedBundle(_AutoListBase):
    target: str
    fetched_at: datetime
    sources: list[SourceItem]

class SourceItem(_AutoListBase):
    source_type: SourceType    # serp | site | pricing | linkedin | jobs | news | review | other
    url: str
    text: str                  # capped at 8000 chars per source
    subject: SourceSubject     # target | self | competitor
    competitor_name: str       # populated when subject == COMPETITOR
    fetched_at: datetime
```

One bundle = one scrape pass. Every downstream agent reads the same `bundle.sources`, which means:
- No duplicate Bright Data charges (the "lean cache" principle from the original brief)
- Every claim's `Citation.snippet` must trace back to *some* `SourceItem.text` — verifiable in O(N) by the grounding guard.

### 4.2 PII guard ([`guardrails/pii.py`](../guardrails/pii.py))

```python
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_CANDIDATE = re.compile(r"\+?\d[\d\s().\-]{7,}\d")

EMAIL_TAG = "[REDACTED-EMAIL]"
PHONE_TAG = "[REDACTED-PHONE]"

def redact(text: str) -> tuple[str, int]:
    # emails → tag; phones → require ≥10 digits before tagging
    # so prices like "$1,234" and headcounts like "12 AEs" never match
```

Conservative by design. On the Orchid self-mode run (with LinkedIn employee profiles in the bundle) this redacts 282 PII instances before any agent sees the text.

### 4.3 Leak / scope guard ([`guardrails/leak.py`](../guardrails/leak.py))

Drops any source containing a confidentiality marker:

```python
_MARKERS = [
    "confidential",
    "do not distribute",
    "internal use only",
    "internal board deck",
    "proprietary and confidential",
    "not for distribution",
    "internal memo",
    "under nda",
]
```

With one V7.26 exemption: **trusted publishers** (FT, Bloomberg, Reuters, WSJ, NYT, Washington Post, Economist, Guardian, Telegraph, BBC, CNBC, Forbes, Business Insider, Fortune, Axios, TechCrunch, The Information, Wired, ArsTechnica) are skipped. They routinely report *on* confidential documents without being confidential themselves — flagging them was a 100% false-positive rate that cost real news-of-record signal.

### 4.4 Grounding guard ([`guardrails/grounding.py`](../guardrails/grounding.py))

Two passes, both in `filter_claims`:

```python
def filter_claims(claims, bundle):
    haystacks = [_norm(t) for t in bundle.texts()]
    kept, dropped = [], []
    for claim in claims:
        if is_grounded(claim, haystacks):                 # claim-level
            kept.append(prune_citations(claim, haystacks)) # cite-level (V7.21)
        else:
            dropped.append(claim.text)
    return kept, dropped
```

- **Claim-level (V4):** at least one citation's snippet (whitespace-normalised, lowercased) must appear verbatim in some source's text. Below `MIN_SNIPPET_LEN = 15` after normalisation, the snippet never grounds — too easy to false-positive on common bigrams like "to the".
- **Cite-level (V7.21):** even if the claim survives, its non-grounded sibling citations are dropped. Previously a true citation could carry a fabricated sibling along for the ride. After V7.21, every rendered citation has been individually verified.

The V7.21 patch caught **14 sibling hallucinations** on the first Supabase brief (the audit + fix are in commit `06ebad9`). The current Supabase brief: **90 citations, 90 grounded, 0 hallucinated** (committed in `data/supabase/brief.json`).

---

## 5. Department agents

Four parallel branches, all with the same shape: read `clean: SharedBundle`, write a typed Pydantic output. Each agent is ~30-50 lines.

### 5.1 GTM (Track 1) — [`agents/gtm.py`](../agents/gtm.py)

Output: `AccountBrief { buying_signals, competitor_moves, hiring_signals, outreach_angle }`.

```python
_PROMPT = """You are the Revenue / GTM department of an enterprise intelligence org.
From the live web sources below about "{target}", extract revenue-relevant signals.

SOURCES:
{context}

Return JSON for an AccountBrief with fields:
- buying_signals: list of {{text, citations:[{{url, snippet, source_type}}], confidence}}
- competitor_moves: same shape
- hiring_signals: same shape
- outreach_angle: one concise sentence a seller could open with
- target: "{target}"

{grounding}
"""
```

The `{grounding}` token expands to the verbatim rule defined in `agents/base.py:GROUNDING_RULE`:

> *"Every claim MUST include at least one citation whose `snippet` is copied VERBATIM from one of the sources above, plus that source's `url`. Do not invent facts. If a signal is not supported by the sources, omit it."*

### 5.2 Finance (Track 2) — [`agents/finance.py`](../agents/finance.py)

Output: `MarketSignal { pricing_trend, expansion_contraction, web_traffic_proxy, vendor_health_flags }`.

### 5.3 Security (Track 3) — [`agents/security.py`](../agents/security.py)

Output: `RiskProfile { exposure_indicators, reputational_signals, regulatory_signals, third_party_risk }`.

### 5.4 Marketing (V7) — [`agents/marketing.py`](../agents/marketing.py)

Output: `MarketingSignal { value_proposition, positioning, brand_voice, content_gaps, channel_signals }`.

Marketing differs from the other three because in self-mode it analyses the *founder's own site* and produces an action plan ("here's how to tighten your value prop"), while in target-mode it captures the target's marketing posture for the strategy synthesiser. Same schema, opposite reader. The mode is carried via `business_context` in the prompt.

---

## 6. Cross-pollination (handoffs + synergies)

After grounding, `cross_node` ([`cascade_graph.py:cross_node`](../agents/cascade_graph.py)) inspects the four cleaned dept outputs and emits two types of cross-references:

- **`HandoffMessage`** — explicit dept → dept context that a real org would send via Slack ("Pricing change detected — adjust outreach timing"). Rules are deterministic, not LLM-driven: if Finance has pricing-trend claims AND GTM has hiring claims, emit a `finance → gtm` handoff.
- **`SynergySignal`** — multi-dept findings ("hiring plus funding signals a growth account — prioritize and resource the outreach"). Also rule-based.

Both ride into the cytoscape graph as curved edges (handoff = solid arrow, synergy = dashed bidirectional). Both anchor into `Citation`s pulled from the contributing dept claims.

---

## 7. Strategy + the 4 framework agents

After cross-pollination, five branches fan out in parallel. They all consume the same grounded dept outputs but emit different deliverables.

### 7.1 Strategy ([`agents/strategy.py`](../agents/strategy.py))

The "Chief of Staff" agent. Takes everything below it (4 dept outputs + synergies + handoffs) and emits a single `StrategicPlan`:

```python
class StrategicPlan(_AutoListBase):
    target: str
    headline: str                          # one-sentence framing
    narrative: str                         # 2-3 paragraph executive write-up
    icp_fit: FitTier                       # high | medium | low
    icp_rationale: str
    deal_size_estimate: str                # "$Xk-$Yk ARR" range
    deal_size_rationale: str
    urgency: str                           # "act this week" | "act this quarter" | "monitor"
    urgency_rationale: str
    recommended_plays: list[StrategicPlay] # 3-5 prioritized
    open_questions: list[str]              # gaps for next research pass
    generated_at: datetime
```

Each `StrategicPlay` has `text`, `priority (1-5, coerced from "urgent"/"high"/"P1"/etc.)`, `timeframe`, `owners (list[dept])`, `rationale`, `citations`. The V7.22-pt3 patch made the strategy plays themselves go through cite-level grounding (the strategy LLM tends to paraphrase rather than copy snippets, so its citations now get pruned the same way dept claims do).

### 7.2 Contradictions ([`agents/contradictions.py`](../agents/contradictions.py))

V7.23. Reads every surviving claim across all four depts and asks the LLM to surface mutually-inconsistent pairs:

```python
class Contradiction(_AutoListBase):
    axis: str                              # "uptime" / "pricing" / "compliance breadth"
    claim_a: str                           # VERBATIM from one dept's claim list
    citations_a: list[Citation]            # lifted from the parent claim
    claim_b: str                           # VERBATIM from another dept's claim list
    citations_b: list[Citation]            # lifted from the parent claim
    severity: int                          # 1-3 (1=phrasing, 3=material conflict)
    summary: str                           # one-sentence framing
```

The agent's prompt forces it to reference claims by their *exact text* — the citations are then attached programmatically from the parent claims via dict lookup. This means the contradictions agent **cannot hallucinate new evidence**; it can only re-frame existing grounded claims. If it returns a `claim_a` or `claim_b` that doesn't match anything, the contradiction is silently dropped (zero evidence on either side = drop).

Live example from the current Supabase brief (committed in `data/supabase/brief.json`):

> **[Compliance Information] severity 3/3** — *"One claim asserts the platform provides robust compliance tools, while another states that the webpage dedicated to security and compliance is broken, which directly undermines the ability to verify the platform's compliance posture."*
>
> - **Source A** (Marketing claim): *"The platform provides robust tools for security, compliance, and enterprise needs, enabling businesses to scale securely and meet industry standards."*
> - **Source B** (Security claim): *"There is a significant content gap regarding security and compliance; the dedicated web page for this information is broken and returns a 404 error."*

This is genuinely useful intelligence — a procurement reviewer who checked this would catch a real credibility gap.

### 7.3 Porter's 5 Forces ([`agents/porter.py`](../agents/porter.py))

V7.24. Output schema:

```python
class FiveForces(_AutoListBase):
    rivalry:        Force        # industry rivalry
    new_entrants:   Force        # threat of new entrants
    supplier_power: Force
    buyer_power:    Force
    substitutes:    Force        # threat of substitutes

class Force(_AutoListBase):
    name: str
    intensity: int               # 1-5, coerced from "low"/"high"/"extreme"
    assessment: str              # 2-3 sentences
    citations: list[Citation]    # cite-level pruning applied
```

Renders as an ECharts radar polygon (5 axes) + 5 cards. On the current Supabase brief: **rivalry 5, buyer_power 4, substitutes 4, new_entrants 3, supplier_power 3**.

### 7.4 SWOT ([`agents/swot.py`](../agents/swot.py))

V7.24. Classic 2×2:

```python
class Swot(_AutoListBase):
    strengths:     list[SwotItem]
    weaknesses:    list[SwotItem]
    opportunities: list[SwotItem]
    threats:       list[SwotItem]

class SwotItem(_AutoListBase):
    text: str
    citations: list[Citation]
    impact: int                  # 1-3, coerced from "minor"/"moderate"/"material"
```

### 7.5 PESTLE ([`agents/pestle.py`](../agents/pestle.py))

V7.26. Macro-environment analysis:

```python
class Pestle(_AutoListBase):
    political:     PestleFactor
    economic:      PestleFactor
    social:        PestleFactor
    technological: PestleFactor
    legal:         PestleFactor
    environmental: PestleFactor

class PestleFactor(_AutoListBase):
    name: str
    pressure: int                # 1-5
    direction: str               # "tailwind" / "headwind" / "neutral"
    assessment: str
    citations: list[Citation]
```

Where Porter is about the *competitive* environment, PESTLE is about the *macro* environment — government, currency, labour market, tech maturity, regulation, climate. On the current Orchid brief (Romanian wind turbine firm): political 5/5 ↑ tailwind (EU Green Deal + post-2022 energy security), environmental 5/5 ↑ tailwind (climate policy), economic 4/5 ↑, technological 4/5 ↑, social 3/5 →, legal 3/5 →.

---

## 8. Grounding guard

See §4.4 above. The full implementation is 60 lines.

The most important property: **the grounding guard is the only adversarial mechanic in Taki, and it is purely defensive.** No agent tries to "beat" another. The pipeline doesn't reward LLMs for finding more signal. The only enforcement is "did the snippet you cited actually appear in the bundle? If not, your claim dies." Everything else is collaborative.

This is intentional. Adversarial multi-agent setups (red team vs blue team, judge vs proposer) sound exciting but in practice produce evaluation overhead with limited information gain on tasks where the ground truth is already on the table (the bundle text). A single verbatim-substring check does the work of a much more elaborate system.

---

## 9. Pydantic schemas + LLM-drift tolerance

[`agents/schemas.py`](../agents/schemas.py) declares 28 Pydantic classes. They're all unified by `_AutoListBase`, which catches the single most common LLM JSON-shape mistake: returning a bare dict for a field declared as `list[...]`:

```python
class _AutoListBase(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _wrap_singletons(cls, data):
        if not isinstance(data, dict):
            return data
        for name, field in cls.model_fields.items():
            ann_str = str(field.annotation)
            if "list[" not in ann_str and "List[" not in ann_str:
                continue
            v = data.get(name)
            if v is None:
                data[name] = []
            elif isinstance(v, dict):
                data[name] = [v]          # singleton dict → 1-element list
            elif isinstance(v, str):
                data[name] = [v]          # singleton string → 1-element list
        return data
```

Together with [`agents/base.py:parse_into`](../agents/base.py), which handles the *other* common mistake — LLMs wrapping their output under a key matching the class name (`{"RiskProfile": {...}, "target": "X"}` instead of `{...}`) — this gives the cascade meaningful resilience to LLM drift without resorting to retries or repair loops.

```python
# agents/base.parse_into (V7.15)
def parse_into(raw: str, schema: type[T]) -> T:
    obj = json.loads(strip_fences(raw))
    try:
        return schema.model_validate(obj)
    except Exception:
        # LLM wrapped output under {"<ClassName>": {...}} alongside sibling keys.
        # Lift the wrapped dict's keys to the top level (outer wins on conflict),
        # then re-validate. Case-insensitive + underscore-stripped class match.
        if isinstance(obj, dict):
            norm_class = schema.__name__.lower().replace("_", "")
            for k in list(obj.keys()):
                if k.lower().replace("_", "") == norm_class and isinstance(obj[k], dict):
                    wrapped = obj.pop(k)
                    merged = {**wrapped, **obj}
                    try:
                        return schema.model_validate(merged)
                    except Exception:
                        pass
        raise
```

Coercion validators handle the rest: `Claim._coerce_confidence` translates `"high"` → `0.85`; `StrategicPlay._coerce_priority` translates `"urgent"`/`"P1"` → `1`; `Contradiction._coerce_severity` translates `"major"` → `3`; `Force._coerce_intensity` translates `"high"` → `4`; `PestleFactor._coerce_direction` translates `"positive"`/`"+"`/`"favorable"` → `"tailwind"`.

---

## 10. Frontend rendering pipeline

The frontend is intentionally minimal: 3 files (`index.html`, `app.js`, `cascade-flow.js`), no build step, all CSS inline in `<style>`.

The render order in [`app.js:render(brief)`](../frontend/app.js) is:

1. `renderStrategicPlan(brief.strategic_plan)` — hero (headline + narrative + flip-in stat cards + collapsible plays)
2. `renderPlanGantt(brief.strategic_plan)` — Gantt timeline (V7.25)
3. `renderBadges(brief.guardrail_report)` — passed/failed pill row
4. `renderDropped(brief.guardrail_report)` — collapsible drawer of every dropped claim
5. `renderCascadeFlow(brief)` — cytoscape graph + pip strip + tip
6. `renderClaimsChart(brief)` — ECharts-GL 3D bar3D (V7.20)
7. `renderSynergies(brief.synergy_signals, brief)` — clickable cards + drawer (V7.19)
8. `renderContradictions(brief.contradictions)` — opposing-source compare cards (V7.23)
9. `renderFiveForces(brief.five_forces)` — radar + cards (V7.24)
10. `renderSwot(brief.swot)` — 2×2 grid (V7.24)
11. `renderPestle(brief.pestle)` — 2×3 grid (V7.26)
12. Department panels (Marketing / GTM / Finance / Security)

Every chart that needs an interactive library uses the existing CDN-loaded ones (cytoscape, GSAP, ECharts, ECharts-GL). The page works fully offline against `frontend/brief.json` — Vercel just serves the static files.

---

## 11. SSE event protocol

When the user clicks `▶ live demo` or `🚀 analyze my business`, the frontend POSTs to `/api/run` and consumes a server-sent-events stream. Every node in the cascade graph emits one or more JSON events to this stream:

```json
{"phase": "serp",          "status": "serp_start",  "query": "..."}
{"phase": "serp",          "status": "serp_done",   "query": "...", "found": 3, "source_type": "review"}
{"phase": "serp",          "status": "tier_summary","tiers": {"T1":4, "T3":3, "T5":3}, "kept": 12}
{"phase": "fetch",         "status": "start",       "mode": "live", "target": "...", "urls": 6}
{"phase": "fetch",         "status": "done",        "sources": 18, "external_added": 12}
{"phase": "pii",           "status": "start"}
{"phase": "pii",           "status": "done",        "redactions": 19}
{"phase": "leak",          "status": "done",        "flags": []}
{"phase": "dept",          "dept": "gtm",           "status": "start"}
{"phase": "dept",          "dept": "gtm",           "status": "done", "claims": 11}
{"phase": "grounding",     "status": "done",        "dropped": 7}
{"phase": "handoff",       "from": "finance",       "to": "gtm", "message": "..."}
{"phase": "synergy",       "depts": ["gtm","finance"], "text": "..."}
{"phase": "strategy",      "status": "done",        "headline": "...", "plays": 4, "icp_fit": "high"}
{"phase": "contradictions","status": "done",        "found": 2}
{"phase": "porter",        "status": "done",        "rivalry": 5, "buyer_power": 4, ...}
{"phase": "swot",          "status": "done",        "s": 4, "w": 3, "o": 4, "t_": 3}
{"phase": "pestle",        "status": "done",        "political": 5, "economic": 4, ...}
{"phase": "assemble",      "status": "done",        "passed": false, "claims": 47}
{"phase": "complete",      "status": "done",        "target": "...", "dropped": 17}
```

[`frontend/cascade-flow.js:_handleLiveEvent`](../frontend/cascade-flow.js) switches on `phase`, updates the pip strip + cytoscape graph, and pipes a one-line summary into the `.cascade-tip` element below the graph. The pip strip starts at `pii` and ends at `strategy` — SERP / fetch happen before the pips light up; contradictions / porter / swot / pestle run in parallel after the strategy pip and don't get their own slot.

---

## 12. Testing strategy

```bash
.venv/bin/python -m pytest -q          # 150 tests, ~15 seconds, fully offline
```

Three layers of coverage:

| Layer | Tests | Approach |
|---|---|---|
| Pure helpers | `test_pii.py`, `test_grounding.py`, `test_leak.py`, `test_url_audit.py`, `test_schemas.py`, `test_schema_coercion.py`, `test_cache.py`, `test_llm.py` | Input → output assertions. No mocks needed. |
| Bright Data layer | `test_brightdata.py`, `test_brightdata_self.py` | Stub `BrightDataClient.unlock` to return canned HTML. Tests the SERP parser, tier classifier, low-tier cap, industry-query routing, error swallowing. |
| Agents + cascade | `test_gtm.py`, `test_finance.py`, ..., `test_cascade_graph.py`, `test_cascade_brief.py`, `test_self_mode.py`, `test_orchestrator.py`, `test_server.py`, `test_run.py` | Inject `fake_*_llm` from `fixtures/fake_llm.py`. The fake LLMs return canned JSON aligned with the Northwind sample bundle — every "claim" in the fake outputs is a snippet that exists verbatim in `fixtures/sample.sample_bundle()`. This makes the full cascade end-to-end deterministic. |

`test_frontend_contract.py` is a special case: it loads `frontend/brief.json` (the cached Vercel deliverable) and asserts every field `app.js` reads is present. So if a future commit changes the schema, the front-of-house breaks at CI time, not at user-facing demo time.

---

## 13. Deployment topology

### What ships on the hosted demo

| Asset | Where | How |
|---|---|---|
| Static dashboard (`index.html`, `app.js`, `cascade-flow.js`) | Vercel free tier | `npx vercel --prod` from `frontend/` (or via GitHub integration when re-enabled) |
| `frontend/brief.json` | bundled into the Vercel static site | Updated by re-running the cascade locally + committing the result |
| Live cascade backend (`server.py`) | local only — by design | Publishing without auth would let strangers drain the Bright Data + Vertex spend cap |

### Local boot

```bash
./demo.sh
# brings the venv online, runs the test suite, starts server.py on :5001
```

Internal layout: `server.py` is a single Flask process that serves the static `frontend/` directory and exposes three API endpoints:

- `GET /api/brief` — return the latest cached `CascadeBrief`
- `GET /api/status` — return the current run state (`running` / `completed` / `error` + last phase + last event)
- `POST /api/run` — start a cascade and return SSE event stream

Three modes route into the same `/api/run` handler:

- `demo` — no keys needed; uses `fixtures/sample.sample_bundle()` + every `fake_*_llm`
- `live` — real Bright Data scrape + real LLM on a target name + URLs (target-mode)
- `self` — real Bright Data scrape + real LLM on a `BusinessProfile` (self-mode w/ sub-page discovery)

The single-slot run lock (`_run_lock`) ensures at most one cascade is in flight at a time — keeps the Bright Data spend predictable on a single-user demo server.

---

# V7.30 → V7.41 — Personalization & infrastructure (delta)

This appendix documents the V7.30 through V7.41 additions on top of the
V7.29-pt3 architecture above. Eleven version bumps that took the system
from "templates + cached briefs" to "truly personalized per-business
analysis for any new target".

## New agents

### `agents/cross_pollinate_llm.py` (V7.35) — replaces templated cross-talk

One LLM call per cascade reading all 4 dept claim sets + `BusinessProfile`
+ sector signal. Emits up to 6 `HandoffMessage` and 4 `SynergySignal`
items whose **content** references the company's actual facts — no more
"Pricing change detected — adjust outreach timing/messaging" identical
across every brief.

Hallucination defense: refs URLs on handoffs + citation URLs on synergies
are filtered against the union of URLs the LLM was actually shown in
the prompt. The LLM CAN'T invent URLs.

`cascade_graph.cross_node` tries the LLM first; if both arrays return
empty, falls back to the deterministic `_templated_cross_pollinate()`
helper (identical behaviour to the pre-V7.35 path). Cascade never ends
up with empty cross-talk.

### `agents/expert_quotes.py` (V7.34) — verbatim attribution layer

One LLM call extracting NAMED-INDIVIDUAL verbatim quotes from the
bundle. Strict prompt: quote text in quotation marks OR clearly
attributed via "said X" / "according to X". Returns `list[ExpertQuote]`
{ name, role, organization, quote, citation }. Capped at 12 quotes per
cascade; dedupes by verbatim text.

Wired serially as `expert_quotes_pass` between `profile_extract` and
`sector_pass` so the post-sector 5-way fan-in into assemble stays
equal-depth (V7.29-pt3 lesson: Vertex degrades on >5-way fan-out).

### `agents/query_generator.py` (V7.36) — dynamic industry SERP queries

One LLM call given `target/industry/region/stage` returns 5-8 highly
tailored Google search queries (with `site:` operators, `filetype:pdf`,
date qualifiers). Replaces the hardcoded `_industry_template_for()`
limit — ANY industry now gets tailored coverage.

Per-(target, industry, region, stage) in-process memo. Same-target
reruns skip the LLM.

Server target-mode (and V7.41 CLI) concat the LLM-generated queries
to `default_external_queries` output before `discover_external_sources`
fires.

### `agents/competitor_summary.py` (V7.38) — post-cascade competitor enrichment

Lightweight implementation of gap #3 (full per-competitor 3-page
cascade was $0.30/run + 4h build; this is $0.15/run + 1d build).

For each name in `business_profile.competitor_names` (capped at 3):

1. SERP for `"{name}" official site` → first non-Google result whose
   hostname plausibly matches the competitor's brand
2. Unlock the URL → V7.30 chrome fallback if SPA-blocked
3. ONE LLM call extracting `CompetitorSummary` { positioning,
   pricing_hint, stage_hint, why_relevant, citation }

`why_relevant` MUST mention the target — forces a relevance statement,
not generic boilerplate.

Runs post-cascade (server.py + run.py) because
`profile_extract.competitor_names` is only populated mid-cascade.

## New BD-layer behaviour

### V7.30 JS-chrome detection + fallback

`services.brightdata.looks_like_js_chrome(text)` runs AFTER
`is_low_quality` passes; trims known SPA boilerplate then flags as
chrome if the trimmed text is `< 1500 chars` OR matches a JS-required
phrase like "you need to enable JavaScript".

`fetch_js_chrome_fallbacks(target, chrome_url, client)` pulls
en.wikipedia.org/{target} + web.archive.org/web/2025/{chrome_url} via
the existing Web Unlocker zone. Returns 0-2 supplementary `SourceItem`
records.

`build_bundle` wires this up via `chrome_fallback=True` and fires AT
MOST ONCE per bundle. Server emits `phase=chrome_fallback` SSE events.

### V7.31 sub-page concept walk

`discover_subpages(base_url, client, subject, ...)` extracted from
the V7.12 self-mode `_expand` closure to a module-level helper. For
each of 11 concept groups (about / projects / references / products /
certifications / news / team / careers / pricing / investors /
research / blog) walks synonym paths in order; first that scrapes +
clears `is_low_quality` wins the concept.

`build_bundle` calls this on `expand_url` (defaults to first user URL)
for target-mode. Server pins `expand_url=user_urls[0][0]` so
SERP-discovered externals never drive expansion.

### V7.33 academic + analyst SERP overlays

`default_external_queries(target, industry, region)` now layers:

1. `base` (2) — filings + newspaper-of-record
2. `academic_queries` (2-5) — Scholar (date-tightened) + Semantic
   Scholar + sector-conditional PubMed/biorxiv / arXiv / SSRN / IEA-IRENA
3. `analyst_queries` (4-5) — Gartner/Forrester/IDC + HN + Reddit +
   LinkedIn pulse + podcast/conference + optional regional overlay
4. `industry_layer` (0-12) — existing per-sector template OR V7.28
   generic fallback

Total: 14-24 queries per cascade (was 15 pre-V7.33).

## New brief surface area

### `CascadeBrief.bundle_stats: Optional[BundleStats]` (V7.37)

```python
BundleStats {
  sources_total:      int
  by_tier:            dict[str, int]   # {"T1": 2, "T2": 1, ...}
  by_subject:         dict[str, int]
  by_source_type:     dict[str, int]
  expanded_subpages:  int   # V7.31 hits
  chrome_fallbacks:   int   # V7.30 hits
  expert_quote_count: int   # V7.34 count
}
```

### `CascadeBrief.expert_quotes: list[ExpertQuote]` (V7.34)

```python
ExpertQuote { name, role, organization, quote, citation }
```

### `CascadeBrief.competitor_summaries: list[CompetitorSummary]` (V7.38)

```python
CompetitorSummary {
  name, url, positioning, pricing_hint, stage_hint,
  why_relevant, citation
}
```

## Cascade topology (V7.41)

```
URL audit → BD fetch (w/ V7.30 chrome + V7.31 sub-pages + V7.33 SERP overlays + V7.36 LLM queries)
    ↓
SharedBundle
    ↓ PII → leak
    ↓ (parallel — 4 dept agents)
[Marketing] [GTM] [Finance] [Security]
    ↓ grounding (claim + cite level)
    ↓ V7.35 cross_pollinate (LLM, fallback templated)
    ↓ profile_extract
    ↓ V7.34 expert_quotes_pass
    ↓ sector_pass (pharma | saas | energy | generic)
    ↓ (parallel — 5 reasoning agents, equal-depth fan-in)
[Strategy] [Contradictions] [Porter] [SWOT] [PESTLE]
    ↓ assemble (+ V7.37 bundle_stats)
    ↓ [post-cascade] V7.38 competitor_summary
    ↓ SSE → cytoscape + dashboard re-render
```

## Frontend deltas

- **V7.32** — dept node labels carry per-brief signal counts; sector
  satellite labels always show `· N` (dim on zero).
- **V7.34** — `renderExpertQuotes` panel above departments.
- **V7.37** — `renderBundleStats` chip strip at top (above plan hero).
- **V7.38** — `renderCompetitorSummaries` card panel.
- **V7.39** — `target-distance-from-node: 0`, `arrow-scale: 1.6`,
  `outside-to-node` clamp. Arrows plug into node borders.
- **V7.40** — source = `cut-rectangle`, brief = bigger + SHU shadow,
  sector edges thinner (`.sector-edge`), per-arc-class label
  `text-margin-y` stagger.

## CLI (V7.41 parity)

```
.venv/bin/python run.py "Target" \
  https://target.com:site https://target.com/pricing:pricing \
  --industry "..." --region "US" --stage "growth" \
  [--no-cache]
```

End-to-end parity w/ `server.py` target-mode.

---

For the design narrative ("why did we build it this way at all"), see [`JOURNEY.md`](JOURNEY.md). For the per-session build log, see [`STATUS.md`](STATUS.md). For the lablab.ai form drafts + video script, see [`PRESENTATION.md`](PRESENTATION.md).
