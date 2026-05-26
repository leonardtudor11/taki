# Taki — The Journey

Built for the [Bright Data — Web Data UNLOCKED](https://lablab.ai/ai-hackathons/brightdata-ai-agents-web-data-hackathon) hackathon by a non-technical founder + Claude Code, end of May 2026. License: MIT.

This document is for judges and anyone reading the repo cold: the problem we set out to solve, the architectural reasoning, how we map to all three Bright Data tracks, what we built version by version, what we learned the hard way, and the roadmap.

---

## 1. The problem

Most "AI for revenue" tools are a single LLM with a single feed. A salesperson types a target → the model emits a paragraph.

Real revenue decisions are cross-functional. Sales, Finance, and Security/Compliance each look at the same account through different lenses, talk to each other, and reach a conclusion that no single lens could produce alone. And for small businesses, the question flips: instead of analysing someone else, the founder wants to analyse *their own* business — competitors, marketing, finance, security, all in one place, with a concrete plan they can execute this week.

Taki models that company, both directions, on one shared live-web data layer.

## 2. The idea — three principles

| Principle | Mechanism |
|---|---|
| **Lean — scrape once** | A `SharedBundle` is the single live-web cache; every department reads it. No redundant Bright Data pulls. |
| **Cascade — model the company** | A LangGraph `StateGraph` runs four dept agents in parallel after guardrails, joins on grounding, cross-pollinates into synergies + handoffs, then synthesizes a Chief-of-Staff plan. |
| **Compliance audits everyone** | Security/Compliance is both a department (producer of `RiskProfile` claims) and the guardrail layer (PII redaction, leak/scope withholding, citation-grounding) — exactly how a real GRC team works. |

## 3. How Taki maps to all three Bright Data tracks

Every track is wired into the same cascade — they're not three separate products, they're three departments of one product. Plus a fourth, Marketing (V7), and a fifth, Strategy (V6), that synthesize across them.

| Track | Department | What it produces | Bright Data zones it pulls |
|---|---|---|---|
| **Track 1 — GTM Intelligence** | Revenue / GTM (`agents/gtm.py`) | `AccountBrief` — buying signals, competitor moves, hiring signals, outreach angle | SERP + Web Unlocker (pricing, careers, news pages) |
| **Track 2 — Finance & Market Intelligence** | Finance / Market (`agents/finance.py`) | `MarketSignal` — pricing trend, expansion/contraction, web-traffic proxy, vendor-health flags | Web Unlocker (pricing pages, jobs-as-alt-data, news, subprocessor lists) |
| **Track 3 — Security & Compliance Intelligence** | Security / Compliance (`agents/security.py`) | `RiskProfile` — exposure indicators, reputational, regulatory, third-party risk · PLUS the 3 guardrails (PII redaction, leak/scope withholding, grounding-citation enforcement) | Web Unlocker (trust pages, subprocessor lists, news, review sites) |
| Synthesis layer | Marketing (V7, `agents/marketing.py`) + Strategy (V6, `agents/strategy.py`) | `MarketingSignal` (value-prop, positioning, brand voice, content gaps, channel signals) + `StrategicPlan` (headline + narrative + ICP fit + deal-size + urgency + 3-5 prioritized plays + open questions) | Reads the 3 dept outputs above — no extra scraping |

The hackathon brief expected one track. We picked Track 1 primary and built Tracks 2 + 3 as feeder departments — because real GTM decisions are not GTM-only. The integration is the differentiator.

## 4. Architecture (the actual graph)

```
Bright Data live web (SERP · Unlocker · Scraper)
         │ scrape once
         ▼
   SharedBundle (Lean cache)
         │
 ┌──── guardrails: Security/Compliance ────┐
 │  PII redaction  ·  leak/scope withhold   │
 └────────────────┬─────────────────────────┘
       clean, public, de-identified
         │
 ┌───────┬───────┼───────┬───────┐
 ▼       ▼       ▼       ▼
Marketing   GTM     Finance   Security      ← 4 dept agents (parallel)
         │
         ▼ grounding guard — drop uncited claims (logged)
         │
         ▼ cross-pollinate → synergy signals + dept handoffs
         │
         ▼ Strategy (Chief of Staff) ──► StrategicPlan
         │
         ▼ assemble
         ▼
       ★ CascadeBrief ★
         │
         ▼ /api/run SSE → cytoscape graph animates in real time
```

Built on **LangGraph `StateGraph`** — explicit parallel fan-out, reducer-merged event list, single-graph compile. Sync nodes; LangGraph's topology shows the parallelism even where the underlying executor serializes the sync calls.

## 5. The five-agent cast

| Agent | File | Role | Prompt mode |
|---|---|---|---|
| Marketing | `agents/marketing.py` | Value-prop, positioning, brand voice, content gaps, channel signals. **Industry-aware**: high-barrier B2B (wind energy, infrastructure, healthcare) gets reference / certification / collaborator-network bias; SaaS/D2C gets funnel/copy/SEO bias. | self · target |
| Revenue / GTM | `agents/gtm.py` | Buying signals, competitor moves, hiring signals, outreach angle. | both |
| Finance / Market | `agents/finance.py` | Pricing trend, expansion/contraction, web-traffic proxy, vendor-health flags. | both |
| Security / Compliance | `agents/security.py` | Exposure indicators, reputational, regulatory, third-party risk. Also owns the upstream PII + leak guardrails. | both |
| Strategy (Chief of Staff) | `agents/strategy.py` | Reads all four dept outputs + synergies + handoffs. Produces `StrategicPlan`: headline · narrative · ICP fit · deal-size · urgency · 3-5 prioritized plays (priority + timeframe + dept owners + citations) · open questions. **Industry-aware**: high-barrier plays focus on reference-portfolio, certifications, joint case studies, conference presence; lower-barrier plays focus on pricing pages, funnels, social proof. | self (founder-facing) · target (CRO-facing) |

## 6. Two modes, same pipeline

| Mode | Audience | Triggered by | Subject of analysis |
|---|---|---|---|
| `target` | Enterprise revenue / sales | `⚡ live run` popover or CLI | someone else's account (sales intel) |
| `self` | Small business owner | `🚀 analyze my business` modal | the founder's own site + competitor URLs |

Same five agents, same LangGraph topology. The `mode` flag (and the founder's `BusinessProfile` form input) reshapes the prompts. The Strategy department writes the plan FOR the founder in self-mode (`you / your business`), or ABOUT a target in target-mode.

V7.12 added depth-page auto-discovery for self-mode: the founder pastes their homepage, we automatically try concept-grouped sub-paths (`/about` · `/projects` · `/case-studies` · `/references` · `/products` · `/technology` · `/certifications` · `/news` and their synonyms) and feed the ones that 200 + clear the quality gate into the same bundle. This is what lets us surface "no installed-project portfolio with named utility customers" instead of "your homepage could use a better H1 tag" for a wind-energy company.

## 7. The guardrails (Compliance auditing everyone)

| Guard | File | What it does | When it fires |
|---|---|---|---|
| PII redaction | `guardrails/pii.py` | Scrubs emails (`*@*.*`) and phone numbers (≥10 digits) from every scraped source BEFORE any LLM sees the text | First, on every source |
| Leak/scope | `guardrails/leak.py` | Withholds any source whose text contains a confidentiality marker (`confidential`, `internal board deck`, `do not distribute`, `under NDA`, ...) | Second, after PII |
| Grounding | `guardrails/grounding.py` | Drops any dept claim whose citation snippet is not present verbatim in the bundle. Logs each dropped claim to the dashboard's "Hallucinations caught" drawer | Per-claim after the four dept agents fire |

V7.6-V7.8 added two more belt-and-suspenders defensive layers around the bundle itself:

| Layer | File | What it does |
|---|---|---|
| URL audit (pre-scrape) | `services/url_audit.py` | Normalises URLs (trim / strip trailing punct / prepend `https://` / lowercase host) + DNS-resolve check (threaded, 3s deadline) — catches typos before they burn a 30s Bright Data timeout |
| Post-scrape quality gate | `services/url_audit.py::is_low_quality` | Drops scraped bodies < 150 chars OR matching 14 error-page patterns (`404 not found`, `access denied`, `just a moment` for Cloudflare, `you have been blocked`, `enable javascript and cookies`, ...) |

## 8. Why this is enterprise-grade

A single-LLM brief is unsafe for enterprise: PII leaks, confidential bleed-through, hallucinations cost trust. Taki was built so a real GRC team would let it into production:

- Every claim is grounded (citation snippet must appear verbatim in the SharedBundle the depts read)
- PII redacted pre-LLM, not post-output
- Confidential-marked sources withheld entirely (not redacted — withheld)
- Citation URLs are scheme-validated on the frontend (no `javascript:` injection)
- `_AutoListBase` Pydantic mixin coerces common LLM JSON-shape drift (singletons → 1-element lists) so the cascade survives minor model drift
- Spend cap on Bright Data calls (`TAKI_BD_SPEND_CAP`) so an unattended run cannot exceed the allocated credit
- Server holds a single-slot run lock so concurrent runs can't race on `brief.json`
- All claims tagged with confidence scores (LLM-supplied, coerced to `[0,1]`)
- 111/111 tests covering offline + live + audit + coercion paths

## 9. The build — V1 to V7.13

| Phase | Commit | What |
|---|---|---|
| S0-S5 (overnight) | initial | scaffold · 3 dept agents · 3 guardrails · LangGraph-less orchestrator · static dashboard · cached Vercel real-LLM run |
| V1.1 | `4fa9955` | identity reset — inline 3-stream 滝 SVG · warm-ink palette · Fraunces+Inter+JBMono · vermilion 朱 accent · stream-lane gutter |
| V3 | `61b3019` | cytoscape cascade graph — 5 nodes (Bright Data / GTM / Finance / Security / brief), entry animation, click-dept focus filter |
| V2 | `47ab3ec` | real LangGraph `StateGraph` — parallel dept fan-out + per-node SSE-friendly event stream |
| V3.2 | `c687915` + `6d5544f` | replay-cascade mode — `▶ replay cascade` button animates from `brief.json` only (no backend needed) |
| V4 | `5b49b94` | UX polish — confidence bars · dropped-claims drawer · ARIA + focus rings · mobile breakpoints |
| demo path | `5cf35d3` | `./demo.sh` one-command boot · `run.py --demo` fixture path |
| V5 live mode | `aec25eb` | `server.py` Flask + flask-cors · `/api/run` SSE endpoint · 3-button toolbar (replay / live demo / live run) · edge-label clarity fix (no `…` clipping, opaque-bg labels, per-edge arc classes) |
| V6 Strategy | `b2470a3` | Chief of Staff agent · `StrategicPlan` (headline / narrative / ICP fit / deal size / urgency / plays / open questions) · hero section above cascade graph · replay + SSE animate the strategy phase |
| V7 SMB pivot | `110733e` | Marketing dept (4th) · self/target modes · `BusinessProfile` form · onboarding modal · `SourceSubject` tagging |
| V7.1-V7.4 | `6fc98b6` | 4-col responsive grid · per-URL skip in `build_self_bundle` · BD timeout 90s→30s · persistent `_LAST_RUN` + `/api/status v2` · sticky status banner with auto-poll · lock follows worker thread (race fix) |
| V7.6-V7.8 | `8ede64a` | URL audit pipeline · post-scrape quality gate · audit SSE events |
| V7.10 | `4cf84a6` | Pydantic `_AutoListBase` singleton-coercer (every BaseModel migrated) — fixed a real `ValidationError × 4` from a live Orchid SRL self-mode run where Gemini returned bare dicts |
| V7.11-V7.13 (this doc) | (this commit) | depth-over-surface prompts (industry-aware) · auto-discover sub-pages (`/about`, `/projects`, `/references`, `/products`, `/certifications`, `/news` + synonyms — first per concept group wins) · JOURNEY.md · README 3-track mapping |

## 10. What we learned (the bumps)

- **Hand-crafted JSON masks LLM drift**. The Vercel cached brief passed every test because we'd hand-written it. The first real LLM run (Orchid SRL self-mode) blew up with `ValidationError × 4` on `MarketingSignal` because the model returned a singleton dict per field instead of a 1-element list. Fix: `_AutoListBase` Pydantic mixin that auto-wraps. Lesson: **schema-level tolerance + test the real LLM output shape, not just the fixture**.
- **Lock lifetime matters more than lock acquisition**. The run-lock was released in the SSE generator's `finally`, which fired when the client refreshed the page. The worker kept running but a second `/api/run` from a refreshed tab acquired the lock, racing on `brief.json`. Fix: lock follows the worker thread, not the SSE stream.
- **A single bad URL must not kill the whole bundle**. Original `build_self_bundle` raised on first scrape failure. With four URLs and BD's 90s × 3-retry timeout, one bad URL froze the whole cascade for >5 minutes. Fix: per-URL try/except + post-run audit log + 30s BD timeout + URL audit step that fast-fails on DNS NXDOMAIN.
- **Page refresh during a long run shows nothing**. Without persistent run state, refresh shows the stale brief.json with zero signal that anything new ran. Fix: `_LAST_RUN` dict mirrored into `/api/status`; sticky status banner on page load auto-polls.
- **Buyers in different sectors decide on different things**. The first Marketing prompt was SaaS-flavoured (SEO, copy, channel mix). When the user pointed it at a wind-energy company, the output recommended SEO tweaks for a sector that buys on reference projects, IEC certifications, and named utility collaborators. Fix: industry-aware prompts that explicitly de-prioritise surface marketing for high-barrier B2B and bias toward proof-of-execution.
- **Depth-pages live at concept-named sub-paths**, not the homepage. Scraping only the homepage missed the projects / references / certifications pages where the actual proof lives. Fix: V7.12 auto-discover via concept-grouped synonym paths.

## 11. What's queued (transparent roadmap)

| Tier | Item | Effort | Cost |
|---|---|---|---|
| viz | per-dept inline visualisations (positioning quadrant for Marketing, compliance scorecard for Security) | medium | none |
| viz | competitor mind-map (user node centred, competitors as satellites with labelled positioning edges) | medium | none |
| audit | per-URL industry-relevance LLM check (verify each scraped page is actually about the founder's industry) | small | +1 LLM call per URL (~$0.001 + 3s latency) |
| audit | LLM-mediated typo correction (`mulhlan.com` doesn't exist → suggest `moelven.com`?) — requires Bright Data SERP zone for verification | medium | ~$0.005 per failed URL |
| interact | on-demand "tell me more about competitor X" deep-dive endpoint (a sub-cascade against the focused competitor) | medium | +full sub-cascade cost |
| copy | LLM-generated homepage / pricing-page suggestions tied to the founder's identified content gaps | small | +1 LLM call per suggestion |
| ops | continuous monitoring (weekly re-scan with delta diff vs the last brief) | medium | full-cascade cost per scan |
| ops | CRM export (Salesforce / HubSpot push) | medium | none |
| ops | parallelise Bright Data scrapes via `ThreadPoolExecutor` | small | none (saves wall-clock) |
| ops | submit to lablab.ai form + record 5-min video (hackathon submission steps) | n/a | n/a |

## 12. License

MIT — see `LICENSE`. Use it, fork it, ship something better.

## 13. The repo

- README.md — 60-second demo, architecture diagram, stack table, toolbar guide
- docs/JOURNEY.md — this file
- docs/STATUS.md — per-session build log (every commit named + tested)
- docs/RESUME.md — resume prompt for any LLM coding agent picking the project up cold
- docs/PRESENTATION.md — lablab.ai form text + 5-minute video script + slide deck outline
- docs/HANDOFF.md — original morning handoff (V1-V5 era)
- agents/ · guardrails/ · services/ · fixtures/ · tests/ · frontend/ — code
- server.py · run.py · demo.sh — entry points

Built by [@leonardtudor11](https://github.com/leonardtudor11) with Claude Code (Opus 4.7), May 2026, in Romania (EU — GDPR applies). One non-technical founder, ~16 active sessions, 111 tests green, MIT.
