# Taki (滝 — "cascade")

**An agentic enterprise for small businesses (and revenue teams) — five AI departments — Marketing, GTM, Finance, Security, and Strategy — cascading live web intelligence into a single executable plan you can act on this week.**

Two modes, same pipeline:
- **🚀 self mode** — paste YOUR business URL + competitor URLs into the onboarding form. Taki scrapes everything live, runs the four-dept cascade, and produces a strategic plan for YOUR business. Built for founders, not enterprise revenue teams.
- **🎯 target mode** — classic — analyze an enterprise account someone might sell to.

🏆 Track · [Bright Data — Web Data UNLOCKED](https://lablab.ai/ai-hackathons/brightdata-ai-agents-web-data-hackathon) — **Tracks 1 + 2 + 3 integrated** (see §How Taki maps to all three Tracks below). · License: MIT · Full reasoning + journey: [`docs/JOURNEY.md`](docs/JOURNEY.md)

---

## 60-second demo (no API keys)

```bash
git clone https://github.com/leonardtudor11/taki && cd taki
./demo.sh
```

That creates a venv, installs deps, runs the 54-test suite, and opens the
dashboard at **http://localhost:5001** with the bundled real Vercel cascade.
The Flask backend (`server.py`) serves both the static frontend and the live
cascade SSE endpoint on the same port.

Four actions available:

| Button | What it does | Needs |
|---|---|---|
| **🚀 analyze my business** (header) | Opens the onboarding form: paste YOUR site URL, business name, stage, goal, customer segment, and a few competitor URLs. Submit → Taki scrapes everything live (your site + each competitor), runs the four-dept cascade + strategy synthesis, produces a strategic plan for YOUR business. | `.env` filled + `server.py` running |
| **▶ replay cascade** (toolbar) | Animate the cached `brief.json` step-by-step (PII → leak → 4 depts → grounding → handoffs → synergies → strategy → assemble). Pure client-side. | nothing — works offline |
| **▶ live demo** (header) | Real backend run through the LangGraph StateGraph on the fixture bundle. Each node fires a real SSE event that drives the cytoscape graph in real time. | `server.py` running |
| **⚡ live run ▾** (toolbar) | Target-mode classic: real Bright Data scrape + LLM call against a target company you type into the popover. | `.env` filled + `server.py` running |

Other interactions:
- **Click a dept node** → other panels dim, that dept's claims stay bright.
- **Hover an edge** → the handoff/synergy full message appears in the strip below the graph.
- **Open the red "Hallucinations caught" drawer** → every ungrounded claim the grounding guard dropped, verbatim.

CLI live run (no UI):
```bash
cp .env.example .env  # fill BRIGHTDATA_API_KEY + zones + GCP_PROJECT_ID
.venv/bin/python run.py "Stripe" \
    https://stripe.com/pricing:pricing \
    https://stripe.com/jobs:jobs
```

## How Taki maps to all three Bright Data Tracks

All three tracks are wired into the same cascade — they're not three separate products, they're three departments of one product (plus Marketing and Strategy added in V7 / V6).

| Track | Department | Output | Bright Data zones it pulls |
|---|---|---|---|
| **Track 1 — GTM Intelligence** | Revenue / GTM (`agents/gtm.py`) | `AccountBrief` — buying / competitor / hiring signals + outreach angle | SERP + Web Unlocker (pricing, careers, news) |
| **Track 2 — Finance & Market Intelligence** | Finance / Market (`agents/finance.py`) | `MarketSignal` — pricing trend, expansion/contraction, web-traffic proxy, vendor health | Web Unlocker (pricing pages, jobs as alt-data, news, subprocessor lists) |
| **Track 3 — Security & Compliance Intelligence** | Security / Compliance (`agents/security.py`) + 3 guardrails | `RiskProfile` — exposure, reputational, regulatory, third-party risk; PLUS PII redaction, leak/scope withholding, citation-grounding enforcement | Web Unlocker (trust pages, subprocessor lists, news, reviews) |
| (Synthesis) | Marketing (V7, `agents/marketing.py`) + Strategy (V6, `agents/strategy.py`) | `MarketingSignal` (value-prop, positioning, brand voice, content gaps, channel signals) + `StrategicPlan` (headline, narrative, ICP fit, deal size, urgency, 3-5 prioritized plays, open questions) | Reads the 3 dept outputs above — no extra scraping |

For the SMB self-mode use case (V7), the same five agents flip subject: instead of analysing someone else, the founder pastes their own URL + a few competitor URLs and gets a plan written FOR them. V7.12 auto-discovers concept-grouped sub-pages (`/projects`, `/references`, `/certifications`, ...) so depth signals — installed-capacity figures, named utility customers, certifications — actually reach the cascade instead of the homepage being the only source.

## What it does

For a target account, three department-agents run on **one shared live-web data layer** (Bright Data) and cascade their findings into each other — mirroring how a real company's departments synchronize — producing a single grounded **Cascade Brief**.

| Department | Output | Live data (Bright Data) |
|---|---|---|
| **Marketing (V7)** | `MarketingSignal` — value proposition · positioning · brand voice · content gaps · channel signals | your own site + any competitor URLs (per source tagged as `self` or `competitor`) |
| Revenue / GTM | `AccountBrief` — buying / competitor / hiring signals + outreach angle | SERP, company site, LinkedIn jobs, news, pricing |
| Finance / Market | `MarketSignal` — pricing trend, expansion, web-traffic proxy, vendor health | pricing trends, jobs-as-alt-data, web-traffic proxy, vendor health |
| Security / Compliance | `RiskProfile` + guardrails — exposure, reputational, regulatory, 3rd-party risk | exposure scan, reputational + regulatory signals, 3rd-party risk |
| **Strategy (Chief of Staff)** | `StrategicPlan` — headline · narrative · ICP fit · deal-size estimate · urgency · 3-5 prioritized plays · open questions | reads the 4 dept outputs + synergies + handoffs — no extra scraping |

## The metaphor → mechanism

- **Lean synergy** — scrape once into a shared cache; all departments consume it. No redundant pulls.
- **Cascade** — orchestrator cascades one objective → department tasks → output flows department→department.
- **Synergy** — cross-pollination pass: each department's output is context for the others.
- **Guardrails** — Security/Compliance audits the others: grounding (no uncited claims), PII redaction, leak/scope (public-web only).

## Architecture

```
                 Bright Data (live web)
              SERP · Unlocker · Scraper zones
                          │  scrape ONCE
                          ▼
                  SharedBundle (Lean cache)
                          │
        ┌─────── guardrails (Security/Compliance) ───────┐
        │   1. PII redaction   2. leak/scope withholding  │
        └─────────────────────┬──────────────────────────┘
                   clean, public, de-identified
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   GTM agent         Finance agent     Security agent
  AccountBrief       MarketSignal       RiskProfile
        └─────────────────┼─────────────────┘
                          ▼
            grounding guard (drop uncited claims)
                          ▼
         cross-pollination → synergy + dept handoffs
                          ▼
              Strategy (Chief of Staff) ──► StrategicPlan
                          │            headline · narrative · ICP fit
                          │            deal size · urgency · plays · open Qs
                          ▼
                   ★ CascadeBrief ★
              (+ GuardrailReport, exec summary)
                          ▼
                   Dashboard / demo
```

## Run / test

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q          # full offline suite (54 tests, no keys)
.venv/bin/python run.py --demo         # generate a fixture brief end-to-end
```

Live runs need `.env` (copy `.env.example`): Bright Data key + zones, plus
either Vertex AI ADC (`GCP_PROJECT_ID`, preferred) or a Gemini AI Studio key
(`GEMINI_API_KEY`). The whole cascade is testable offline because every LLM
and the web layer are dependency-injected.

## Stack

| Layer | Tech | Why |
|---|---|---|
| Live web | **Bright Data** SERP + Web Unlocker | bot-bypassable, fresh, scope-bounded by spend cap |
| LLM | Gemini 2.5 Pro via **Vertex AI (ADC)** | enterprise-safe — no JSON service-account keys |
| Orchestration | **LangGraph** `StateGraph` | explicit parallel dept fan-out + per-node event stream |
| Data contract | **Pydantic v2** | every claim grounded to a snippet that exists in the bundle |
| Frontend | static HTML/JS + **cytoscape.js** + **GSAP** (CDN) | zero build step; drag-drop deploy on Vercel free tier |
| Live backend | **Flask** + Server-Sent Events | one-process unified static + `/api/run` SSE stream that drives the cytoscape animation in real time |
| Tests | **pytest** + injectable LLM fakes | 54/54 green, fully offline |

## Status

See [`docs/STATUS.md`](docs/STATUS.md) — updated after every session.

## Publish to GitHub (judges-ready)

The repo carries everything a hackathon judge needs to evaluate it: the
[journey + reasoning](docs/JOURNEY.md), the [build log](docs/STATUS.md),
the [lablab form text + 5-min video script](docs/PRESENTATION.md), the
MIT licence, 117 tests, and a one-command demo. To put it public:

```bash
# one-time: install the GitHub CLI + log in
brew install gh
gh auth login

cd ~/taki
gh repo create leonardtudor11/taki \
    --public --license MIT --source=. --remote=origin --push \
    --description "Agentic enterprise on Bright Data live web — 5 AI departments cascading into one strategic plan. SMB self-analysis + enterprise target-account modes. Bright Data Web Data UNLOCKED hackathon (Tracks 1+2+3)."
```

Then add the topics for discoverability:
```bash
gh repo edit --add-topic bright-data,langgraph,multi-agent,b2b,smb,gtm,marketing,security,compliance,hackathon,lablab,pydantic,flask,cytoscape,vertex-ai
```

## License

MIT
