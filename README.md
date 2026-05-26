# Taki (滝 — "cascade")

**An agentic enterprise: departments as AI agents, cascading live web intelligence toward a single revenue deliverable.**

🏆 Track · [Bright Data — Web Data UNLOCKED](https://lablab.ai/ai-hackathons/brightdata-ai-agents-web-data-hackathon) (GTM-primary; Finance + Security as feeder departments)

---

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
.venv/bin/python -m pytest -q        # full offline suite (fixtures, no keys)
```

Live runs need `.env` (copy `.env.example`): Bright Data key + zones, a Gemini
key. The whole cascade is testable offline because every LLM and the web layer
are dependency-injected.

## Status

See [`docs/STATUS.md`](docs/STATUS.md) — updated after every session.

## License

MIT
