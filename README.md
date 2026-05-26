# Taki (滝 — "cascade")

**An agentic enterprise: departments as AI agents, cascading live web intelligence toward a single revenue deliverable.**

🏆 Track · [Bright Data — Web Data UNLOCKED](https://lablab.ai/ai-hackathons/brightdata-ai-agents-web-data-hackathon) (GTM-primary; Finance + Security as feeder departments)

---

## 60-second demo (no API keys)

```bash
git clone https://github.com/leonardtudor11/taki && cd taki
./demo.sh
```

That creates a venv, installs deps, runs the 54-test suite, and opens the
dashboard at **http://localhost:8000** with the bundled real Vercel cascade.

Once it's open:
- **Click a dept node** in the cytoscape graph → other panels dim, that
  dept's claims stay bright.
- **Hover an edge** → the handoff/synergy message expands in the strip below.
- **▶ replay cascade** → watch the pipeline animate from PII → leak guard →
  parallel dept agents → grounding → handoffs → synergies → assemble.
- **Open the red "Hallucinations caught" drawer** → see every ungrounded
  claim the grounding guard dropped before it could reach the brief.

For a live run against your own target:
```bash
cp .env.example .env  # fill BRIGHTDATA_API_KEY + zones + GCP_PROJECT_ID
.venv/bin/python run.py "Stripe" \
    https://stripe.com/pricing:pricing \
    https://stripe.com/jobs:jobs
```

## What it does

For a target account, three department-agents run on **one shared live-web data layer** (Bright Data) and cascade their findings into each other — mirroring how a real company's departments synchronize — producing a single grounded **Cascade Brief**.

| Department | Track | Output | Live data (Bright Data) |
|---|---|---|---|
| Revenue / GTM | 1 | `AccountBrief` | SERP, company site, LinkedIn jobs, news, pricing |
| Finance / Market | 2 | `MarketSignal` | pricing trends, jobs-as-alt-data, web-traffic proxy, vendor health |
| Security / Compliance | 3 | `RiskProfile` + guardrails | exposure scan, reputational + regulatory signals, 3rd-party risk |

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
| Tests | **pytest** + injectable LLM fakes | 54/54 green, fully offline |

## Status

See [`docs/STATUS.md`](docs/STATUS.md) — updated after every session.

## License

MIT
