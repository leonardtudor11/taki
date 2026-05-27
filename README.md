<div align="center">

# Taki (滝 — *"cascade"*)

**Five AI departments cascading live web intelligence into one grounded strategic plan.**

*Built for the Bright Data — Web Data UNLOCKED hackathon. Tracks 1 + 2 + 3 in a single product.*

[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-150%20passing-brightgreen)](#tests)
[![Stack](https://img.shields.io/badge/stack-Python%203.14%20%C2%B7%20LangGraph%20%C2%B7%20Pydantic%20v2%20%C2%B7%20Flask%20%C2%B7%20Bright%20Data-black)](#tech-stack)

🌐 **Live demo:** [`frontend-sage-pi.vercel.app`](https://frontend-sage-pi.vercel.app)
📓 **Build journey:** [`docs/JOURNEY.md`](docs/JOURNEY.md) · **Deep architecture:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

</div>

---

## Why Taki

Most "research agents" hand you a paragraph of plausible-sounding text and a bibliography that crumbles on click. Taki is built around the opposite default: **every claim that lands in the final brief has been verified against a snippet that actually exists in the scraped bundle**. Anything else gets dropped on the floor.

On top of that grounding floor, ten agents cascade — four departments + Strategy synthesiser + Contradictions auditor + three classic strategy frameworks (Porter's 5 Forces, SWOT, PESTLE) — all reading the same scraped Bright Data bundle, all producing citation-anchored output, all rendered into a single dashboard.

**Two modes share the same pipeline:**

| Mode | Use case | Input |
|---|---|---|
| **🚀 self** | A founder analysing their own business + competitors. Surfaces value-prop gaps, hiring tells, pricing tensions, regulatory pressures. | Your URL, your industry, a few competitor URLs |
| **🎯 target** | A revenue / strategy team profiling an account they might sell to (or buy from). | Target name + 5-10 seed URLs |

Both modes also run **industry-aware SERP discovery** — the pipeline derives extra queries from your industry (wind energy → IRENA + IEA + EU Green Deal; backend-as-a-service → Gartner + Forrester + market-size reports) and pulls those into the same bundle through Bright Data's Web Unlocker.

---

## 60-second demo (no API keys)

```bash
git clone https://github.com/leonardtudor11/taki && cd taki
./demo.sh
```

That creates a venv, installs deps, runs the 150-test suite, and boots the dashboard at **http://localhost:5001** against a cached real cascade (Orchid SRL — a Romanian wind-turbine firm).

Three demo flows are wired into the page:

| Button | What it does | Needs |
|---|---|---|
| **▶ replay cascade** | Animate the cached `brief.json` step-by-step in the cytoscape graph (pii → leak → 4 depts → grounding → handoffs → synergies → strategy → assemble). Pure client-side. | nothing — works offline |
| **▶ live demo** | Real backend run through the LangGraph state graph against the bundled Northwind fixture + the fake LLMs (`fixtures/fake_llm.py`). Every node fires real SSE events that drive the graph animation. | `server.py` running |
| **🚀 analyze my business** | Self-mode: paste your URL + industry + competitor URLs. Triggers a real Bright Data scrape + LLM cascade end-to-end. ~3-5 min. | `.env` filled in (see [Configuration](#configuration)) |

> **About the backend.** `server.py` is intentionally local-only. The hosted Vercel page serves the static dashboard + cached `brief.json` so anyone can click through the full output. Live cascades run on your laptop because publishing `/api/run` without auth would let strangers drain your Bright Data + Vertex spend cap.

---

## What you'll see on the dashboard

Top to bottom, the page renders 11 sections, all driven by the single `frontend/brief.json` shipped at deploy time:

1. **Strategic plan hero** — headline · narrative · ICP-fit / deal-size / urgency stat cards (with count-up animation) · 3-5 prioritized plays, P1 expanded by default, click-to-expand on the rest
2. **Gantt timeline** — bars across a 0-180 day scale, color-coded by primary owner dept · click a bar to scroll-to and expand the matching play card
3. **Cascade flow** — phase pip strip + cytoscape graph (Bright Data → 4 depts → brief) · the `▶ replay cascade` button animates the entire pipeline live
4. **3D claim-breakdown chart** — ECharts-GL `bar3D` showing grounded claim counts per (dept × signal type)
5. **Synergies** — clickable cards that open a side drawer with the grounding citations + every related claim across all four depts
6. **Contradictions** — opposing-source pairs surfaced by a dedicated agent (e.g. *"company's marketing claims HIPAA out of the box"* vs *"pricing page says HIPAA is enterprise-tier only"*)
7. **Porter's 5 Forces** — ECharts radar polygon + 5 force cards with intensity meters (1-5) and grounded assessments
8. **SWOT** — 2×2 quadrant grid with per-cell items + impact-colored left borders
9. **PESTLE** — 2×3 macro-environment grid · each factor has pressure 1-5 + direction (tailwind ↑ / headwind ↓ / neutral →) + citations
10. **Department panels** — Marketing / GTM / Finance / Security · claim cards with hover-lift + dept-color glow + verified citation chips
11. **Dropped claims drawer** — every claim the grounding guard killed, verbatim, with the snippet the LLM tried to slip past

Every citation chip is a real outbound link. On the current Orchid brief, citations resolve to **IRENA** publications, **IEA** European wind statistics, the Stockholm Environment Institute, the European Environmental Bureau, the EU Green Deal policy archive, WindEurope industry events, and the Romanian energy trade press (`energynomics.ro`) — among others.

---

## Architecture

```
                       Bright Data (live web)
                  SERP · Web Unlocker · Scraper zones
                                │
              ┌─────────────────┴─────────────────┐
              ▼                                   ▼
  user-supplied seed URLs           SERP-discovered external URLs
   (target's own pages,             (industry-aware: filings, news of
    competitors, etc.)               record, scholar, regulator, trade)
              │                                   │
              └─────────────────┬─────────────────┘
                                ▼
                    tier classifier (T1-T6)
                    cap T5+T6 ≤ 30% · drop BLOCKED
                                ▼
                       SharedBundle (one fetch)
                                │
              ┌── guardrails (Security / Compliance) ──┐
              │   1. PII redaction (emails + phones)    │
              │   2. leak/scope (confidentiality scan,  │
              │      with trusted-publisher exemption)  │
              └─────────────────┬──────────────────────┘
                       clean, de-identified
                                ▼
          ┌──────────┬───────────┼───────────┬──────────┐
          ▼          ▼           ▼           ▼          ▼
        Marketing   GTM       Finance    Security   (parallel)
       Signal      Brief      Signal     Profile
          └──────────┴───────────┼───────────┴──────────┘
                                 ▼
                grounding guard (claim-level + V7.21 cite-level)
                  drop unverified claims · prune sibling cites
                                 ▼
                  cross-pollination (handoffs + synergies)
                                 │
       ┌─────────────┬───────────┼───────────┬──────────────┐
       ▼             ▼           ▼           ▼              ▼
    strategy    contradictions  porter      swot          pestle
   plan +       opposing-       5 forces    2×2          6 macro
   plays        source pairs                              factors
       └─────────────┴───────────┼───────────┴──────────────┘
                                 ▼
                          CascadeBrief
                  (+ GuardrailReport, exec summary)
                                 ▼
                       Dashboard / brief.json
```

The whole thing is a [LangGraph `StateGraph`](agents/cascade_graph.py) — every node is testable in isolation, every LLM is dependency-injected, and the 150-test suite runs entirely offline through `fixtures/fake_llm.py`.

---

## How it works — pipeline walkthrough

### 1. Bundle assembly

For target-mode (`server.py:373` onward), the user supplies a target name + a few seed URLs. The pipeline derives industry-aware extra queries and unlocks each result through Bright Data:

```python
# server.py — live mode
serp_queries = default_external_queries(target, industry=industry, region=region)
external = discover_external_sources(
    target=target,
    client=client,
    queries=serp_queries,
    exclude_hosts=target_hosts,   # don't re-fetch the target's own domain
    n_per_query=3,
    on_event=_emit_serp,
)
bundle = build_bundle(target, client, user_urls + external)
```

`default_external_queries` (in [`services/brightdata.py`](services/brightdata.py)) layers three tiers of queries:

```python
def default_external_queries(target, industry=None, region=None):
    base = [
        (f'"{target}" filetype:pdf annual report OR 10-K OR prospectus',  SourceType.NEWS),
        (f'"{target}" "Financial Times" OR Reuters OR Bloomberg',         SourceType.NEWS),
        (f'"{target}" site:scholar.google.com OR site:arxiv.org OR study', SourceType.OTHER),
    ]
    # industry layer: wind/solar/saas/biotech/fintech/manufacturing routing
    # region layer: Romania → "Romania OR EU OR Eastern Europe", etc.
    ...
```

For **wind energy** in Romania this expands into queries like `'"{target}" IRENA OR "wind energy"'`, `site:iea.org OR site:irena.org "wind" Romania`, `'"EU Green Deal" wind OR renewable 2024 OR 2025'`. For **backend-as-a-service** it expands into Gartner / Forrester / Postgres-ecosystem queries instead. The full template list is in [`services/brightdata.py:_INDUSTRY_QUERIES`](services/brightdata.py).

### 2. Tier classifier — kills the Reddit monoculture

Every URL Google returns gets classified into one of seven tiers before scraping:

| Tier | Examples | Weight |
|---|---|---|
| **T1** Regulator | `*.gov`, `*.europa.eu`, `sec.gov`, `eur-lex.europa.eu`, `iea.org`, `irena.org`, `oecd.org`, `imf.org`, `worldbank.org`, `transelectrica.ro` | 1.00 |
| **T2** Academic | `scholar.google.com`, `nature.com`, `arxiv.org`, `pubmed.ncbi.nlm.nih.gov`, `*.edu`, `sei.org` (Stockholm Env Inst), `eeb.org`, `bruegel.org` | 1.00 |
| **T3** News-of-record + analyst | `ft.com`, `bloomberg.com`, `reuters.com`, `wsj.com`, `economist.com`, `gartner.com`, `forrester.com`, `mckinsey.com` | 0.85 |
| **T4** Trade publication | `techcrunch.com`, `theinformation.com`, `hpcwire.com`, `windpowermonthly.com`, `windeurope.org`, `energynomics.ro`, `redmonk.com` | 0.70 |
| **T5** Community | `reddit.com`, `news.ycombinator.com`, `medium.com`, `linkedin.com` (**capped at ≤30% of the bundle**) | 0.40 |
| **T6** Review aggregator | `g2.com`, `trustpilot.com`, `capterra.com`, `glassdoor.com` (capped together with T5) | 0.50 |
| **BLOCKED** | `blogspot.com`, `wordpress.com`, `facebook.com`, `instagram.com`, `tiktok.com` | dropped |

```python
# services/brightdata.py
def classify_url(url: str) -> str:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    for s in _BLOCKED_SUFFIXES:
        if host == s or host.endswith("." + s):
            return "BLOCKED"
    for tier, suffixes in _TIER_SUFFIXES.items():
        for s in suffixes:
            if host == s or host.endswith("." + s) or host.endswith(s):
                return tier
    return T0_UNKNOWN
```

**Concrete impact on a real Supabase run** (committed in `data/supabase/brief.json`):

| Metric | Pre-V7.22 (manual URLs only) | Current (V7.26 pipeline) |
|---|---|---|
| Unique citation domains | 1 (`supabase.com` 100%) | 9 (incl. Reuters, Bloomberg, HPCWire, futuremarketinsights, technavio, supabase.com 54%) |
| Reddit share | n/a (no SERP) | **4.4%** |
| T5 community share total (Reddit + LinkedIn combined) | n/a | **14.4%** (cap is 30%) |
| T3 news-of-record share (Reuters / Bloomberg / etc.) | 0% | **11.1%** |

The full audit is reproducible: the cite-by-cite tier breakdown lives in `data/supabase/brief.json` and `data/orchid-srl/brief.json`; the classifier is in [`services/brightdata.py:classify_url`](services/brightdata.py).

### 3. Guardrails — three layers

| Guard | What it does | File |
|---|---|---|
| **PII redaction** | Strip emails + phone numbers (≥10 digits) from every scraped source before the LLMs see it. Conservative — never touches prices, headcounts, dates. | [`guardrails/pii.py`](guardrails/pii.py) |
| **Leak / scope** | Drop any source containing a confidentiality marker (`"confidential"`, `"do not distribute"`, `"under nda"`, etc.). **V7.26 exemption:** trusted publishers (FT, Bloomberg, Reuters, etc.) are skipped — they *report on* confidentiality without being confidential themselves, so flagging them was a 100% false-positive rate. | [`guardrails/leak.py`](guardrails/leak.py) |
| **Grounding (V4 + V7.21)** | Claim-level: a claim survives only if ≥1 citation snippet appears verbatim in the bundle (whitespace-normalised, ≥15 chars). Cite-level (V7.21): even surviving claims have their unverified sibling citations pruned. | [`guardrails/grounding.py`](guardrails/grounding.py) |

The grounding implementation is short enough to print:

```python
# guardrails/grounding.py
MIN_SNIPPET_LEN = 15

def _cite_is_grounded(cite, haystacks: list[str]) -> bool:
    snippet = _norm(cite.snippet)
    if len(snippet) < MIN_SNIPPET_LEN:
        return False
    return any(snippet in h for h in haystacks)

def filter_claims(claims, bundle):
    haystacks = [_norm(t) for t in bundle.texts()]
    kept, dropped = [], []
    for claim in claims:
        if is_grounded(claim, haystacks):
            kept.append(prune_citations(claim, haystacks))  # drop bad siblings
        else:
            dropped.append(claim.text)
    return kept, dropped
```

The most recent Supabase audit (committed in `data/supabase/brief.json`): **90 citations checked → 90 grounded → 0 hallucinated**. The Orchid audit (`data/orchid-srl/brief.json`): **79 / 79 / 0**.

### 4. Department fan-out (parallel)

Once the clean bundle is ready, four department agents run in parallel. Each consumes the same `SharedBundle`, produces a typed Pydantic output, and emits SSE phase events:

| Agent | File | Output schema |
|---|---|---|
| **GTM** (Track 1) | [`agents/gtm.py`](agents/gtm.py) | `AccountBrief` — buying / competitor / hiring signals + outreach angle |
| **Finance** (Track 2) | [`agents/finance.py`](agents/finance.py) | `MarketSignal` — pricing trend, expansion/contraction, web-traffic proxy, vendor health |
| **Security** (Track 3) | [`agents/security.py`](agents/security.py) | `RiskProfile` — exposure, reputational, regulatory, 3rd-party risk |
| **Marketing** (V7) | [`agents/marketing.py`](agents/marketing.py) | `MarketingSignal` — value prop, positioning, brand voice, content gaps, channel signals |

All four are dependency-injectable — the cascade graph passes whichever `llm` callable you give it. In tests we pass `fake_*_llm` functions from [`fixtures/fake_llm.py`](fixtures/fake_llm.py); in production they use Vertex AI Gemini 2.5 Pro via ADC.

### 5. Cross-pollination + framework agents (parallel)

After grounding, two passes run:

**Cross-pollination** ([`cascade_graph.py:cross_node`](agents/cascade_graph.py)) — emits explicit `HandoffMessage` (e.g. `finance → gtm: "pricing change detected — adjust outreach timing"`) and `SynergySignal` (e.g. `gtm + finance: "hiring plus funding signals a growth account"`).

Then **five parallel branches** fan out:

| Branch | File | What it produces |
|---|---|---|
| `strategy` | [`agents/strategy.py`](agents/strategy.py) | `StrategicPlan` — headline + narrative + ICP fit + 3-5 prioritized plays + open questions |
| `contradictions_pass` | [`agents/contradictions.py`](agents/contradictions.py) | `list[Contradiction]` — claim pairs that disagree across sources (axis, severity 1-3, summary, both sides' citations) |
| `porter_pass` | [`agents/porter.py`](agents/porter.py) | `FiveForces` — 5 forces × intensity 1-5 × grounded assessment |
| `swot_pass` | [`agents/swot.py`](agents/swot.py) | `Swot` — 2×2 with impact 1-3 per item |
| `pestle_pass` | [`agents/pestle.py`](agents/pestle.py) | `Pestle` — 6 macro factors × pressure 1-5 × direction (tailwind/headwind/neutral) |

All five join into `assemble_node` which packs everything into a single `CascadeBrief`.

### 6. The CascadeBrief

The deliverable is one Pydantic object with everything inside it:

```python
# agents/schemas.py (selected fields)
class CascadeBrief(_AutoListBase):
    target: str
    mode: CascadeMode
    business_profile: Optional[BusinessProfile] = None
    account_brief: Optional[AccountBrief] = None
    market_signal: Optional[MarketSignal] = None
    marketing_signal: Optional[MarketingSignal] = None
    risk_profile: Optional[RiskProfile] = None
    synergy_signals: list[SynergySignal]
    handoffs: list[HandoffMessage]
    contradictions: list[Contradiction]
    five_forces: Optional[FiveForces] = None
    swot: Optional[Swot] = None
    pestle: Optional[Pestle] = None
    guardrail_report: GuardrailReport
    executive_summary: str
    strategic_plan: Optional[StrategicPlan] = None
```

Pydantic models all the way down — every field is typed, validators handle the LLMs' common JSON-shape drift (`_AutoListBase` wraps singleton dicts into lists; `_coerce_intensity`/`_coerce_severity`/`_coerce_direction` translate `"high"`/`"major"`/`"tailwind"` into the right enum or int).

### 7. Frontend

Static HTML + vanilla JS, served by the same Flask process (`server.py`). No build step. CDN-loaded libraries:

- **cytoscape.js** — the cascade graph (Bright Data → depts → brief)
- **GSAP** — pip-strip animation timings
- **ECharts** + **ECharts-GL** — the 3D claim chart + Porter's radar
- (Nothing else.)

The page reads `frontend/brief.json` on load and renders all 11 sections client-side. The same brief shape powers both the **cached replay** (offline-friendly demo) and the **live SSE animation** (real backend run).

---

## Configuration

Live cascades need `.env` (copy from `.env.example`):

```bash
# Bright Data (required for live + self modes)
BRIGHTDATA_API_KEY=brd_...
BRIGHTDATA_UNLOCKER_ZONE=your_unlocker_zone_name
BRIGHTDATA_SERP_ZONE=your_serp_zone_name        # optional — falls back to unlocker
BRIGHTDATA_SCRAPER_ZONE=your_scraper_zone_name  # optional

# LLM — pick one:
GCP_PROJECT_ID=your-gcp-project    # preferred — Vertex AI via ADC, no JSON keys
# or
GEMINI_API_KEY=AIzaSy...           # AI Studio fallback

# Optional spend cap (Bright Data charges per request)
TAKI_BD_SPEND_CAP=5.00
```

`./demo.sh` will print which subset of modes is unlocked based on what's set. The offline pytest suite needs none of these.

---

## Tech stack

| Layer | Tech | Why |
|---|---|---|
| Live web data | **Bright Data** SERP zone + Web Unlocker zone | bot-bypass, JS-rendering, scope-bounded by `SpendTracker` cap |
| LLM | **Gemini 2.5 Pro** via **Vertex AI (ADC)** | enterprise-safe — no service-account JSON keys on disk |
| Agent runtime | **LangGraph** `StateGraph` | explicit parallel fan-out + per-node event stream + deterministic topology |
| Data contract | **Pydantic v2** | every claim is a typed `Claim` with a typed `Citation` that grounds against the bundle |
| HTTP | **httpx** + **tenacity** | retry-on-flake for Bright Data, no thread pool surprises |
| Backend | **Flask** + Server-Sent Events | one process serves the static dashboard and the `/api/run` SSE stream |
| Frontend | static HTML / JS / CSS + CDN libs (cytoscape, GSAP, ECharts) | zero build step, drag-drop deploy to Vercel free tier |
| Tests | **pytest** + injected fake LLMs in `fixtures/fake_llm.py` | 150 tests, fully offline, no external calls |

---

## <a name="tests"></a>Tests

```bash
.venv/bin/python -m pytest -q
# 150 passed
```

26 test files across:

- **Schema coercion** (`test_schema_coercion.py`) — singleton→list, snake_case unwrapping, hybrid-wrap merge
- **Guardrails** (`test_pii.py`, `test_leak.py`, `test_grounding.py`) — including the V7.21 cite-level pruning regression tests
- **Bright Data** (`test_brightdata.py`, `test_brightdata_self.py`) — payload shape, spend cap, source-tier classifier, SERP HTML parsing, industry-aware query routing
- **URL audit** (`test_url_audit.py`) — pre-scrape normalisation + DNS + post-scrape quality gate
- **Each agent** (`test_gtm.py`, `test_finance.py`, `test_marketing.py`, `test_security.py`, `test_strategy.py`, `test_contradictions.py`)
- **Orchestration** (`test_cascade_graph.py`, `test_cascade_brief.py`, `test_cross_pollinate.py`, `test_orchestrator.py`)
- **Mode-specific** (`test_self_mode.py`, `test_subpage_expansion.py`)
- **HTTP layer** (`test_server.py`, `test_run.py`)
- **Frontend contract** (`test_frontend_contract.py`) — ensures `brief.json` carries every field `app.js` reads

25 test files in total.

Every cascade test path uses fake LLMs — the suite finishes in ~15 seconds with no network calls, no API keys.

---

## Project structure

```
taki/
├── agents/
│   ├── base.py              — shared helpers (parse_into w/ schema-wrap unwrapping, V7.15)
│   ├── schemas.py           — Pydantic data contracts (28 classes, V7.26)
│   ├── cascade_graph.py     — LangGraph StateGraph + parallel fan-out (V7.26: 14 nodes)
│   ├── gtm.py · finance.py · security.py · marketing.py — Track 1/2/3 + V7 dept agents
│   ├── strategy.py          — V6 "Chief of Staff" synthesiser → StrategicPlan
│   ├── contradictions.py    — V7.23 opposing-source pair detector
│   ├── porter.py            — V7.24 Porter's Five Forces
│   ├── swot.py              — V7.24 SWOT 2×2
│   ├── pestle.py            — V7.26 PESTLE macro-environment
│   └── orchestrator.py      — legacy sequential orchestrator (kept for reference)
├── guardrails/
│   ├── pii.py               — email + phone redaction
│   ├── leak.py              — confidentiality scan w/ trusted-publisher exemption (V7.26)
│   └── grounding.py         — claim + cite-level (V7.21) snippet verification
├── services/
│   ├── brightdata.py        — Bright Data client, source-tier classifier (V7.26),
│   │                          industry-aware query templates (V7.26),
│   │                          SERP discovery + low-tier cap (V7.22)
│   ├── url_audit.py         — V7.6 pre-scrape normalize + DNS + post-scrape quality gate
│   ├── llm.py               — Vertex AI ADC + Gemini AI Studio fallback
│   └── cache.py             — bundle + brief disk cache
├── frontend/
│   ├── index.html           — single-page dashboard, all CSS inline
│   ├── app.js               — 11-section render pipeline
│   ├── cascade-flow.js      — cytoscape + SSE event handler + replay timer
│   └── brief.json           — cached deliverable shipped to Vercel
├── fixtures/
│   ├── sample.py            — Northwind sample SharedBundle for offline demos
│   └── fake_llm.py          — canned LLM outputs for tests + `./demo.sh` live demo
├── tests/                   — 26 files, 150 tests, fully offline
├── data/                    — per-target output cache (bundle.json + brief.json per slug)
├── docs/
│   ├── JOURNEY.md           — judge-facing narrative (why each design choice happened)
│   ├── ARCHITECTURE.md      — deep technical reference
│   ├── PRESENTATION.md      — lablab.ai form drafts + 5-min video script
│   ├── STATUS.md            — per-session build log
│   ├── RESUME.md            — fresh-session resume prompt
│   └── HANDOFF.md            — original V1-V5 era handoff
├── server.py                — Flask backend, SSE `/api/run`, serves frontend/
├── run.py                   — CLI live-run entrypoint
└── demo.sh                  — one-command demo bootstrap
```

---

## Roadmap (deferred for post-hackathon)

- **Backend on a free public host** (Cloud Run preferred — same GCP project as Vertex). Requires bearer-token auth + Cloudflare rate-limit before going public, to keep Bright Data spend bounded.
- **Per-claim research dossier page** — click a citation chip → a dedicated route shows the exact snippet, the surrounding paragraph from the bundle, the URL, and the timestamp.
- **More industry templates** — currently shipping wind / solar / renewable / backend / database / saas / biotech / health / fintech / manufacturing. Easy to add: drop a new entry into `_INDUSTRY_QUERIES`.
- **Specialised SERP routes** — google.com today; Google Scholar dedicated route + SEC EDGAR pull for US public companies.
- **Continuous monitoring** — weekly re-scan with delta diff, so a target / self-mode brief becomes a living document.
- **CRM export** — Salesforce / HubSpot push of the strategic plan.

---

## Licence

[MIT](LICENSE) © 2026 Mirel Leonard Tudor.

Built for the [Bright Data — Web Data UNLOCKED](https://lablab.ai/ai-hackathons/brightdata-ai-agents-web-data-hackathon) hackathon.

For the full design narrative — every decision, every dead-end, every fix — read [`docs/JOURNEY.md`](docs/JOURNEY.md). For the deep technical reference (graph topology, prompt design, schemas, frontend internals), read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
