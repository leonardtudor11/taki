# Taki — Resume prompt (paste into a fresh Claude Code session)

Copy everything inside the fence below into the first message of the new
session. The prompt is self-contained: locates the repo, restarts the
backend, names the current state, points at the next pieces of work.

---

```
You are resuming work on **Taki** — Bright Data "Web Data UNLOCKED"
hackathon project that pivoted (V7) into a small-business self-analysis
product with the original target-account mode preserved. Repo lives at
`/Users/mirel-leonardtudor/taki`. Stay strictly inside that directory.

## Boundary (security)
- Only read/write/run inside /Users/mirel-leonardtudor/taki.
- No personal files, no other projects, no ~/.env, no SA keys.
- Every session ends in a `git commit`.

## Boot
```bash
cd ~/taki
# kill any stale server, restart the backend (serves static + /api/run SSE)
lsof -nP -iTCP:5001 -sTCP:LISTEN -t 2>/dev/null | xargs -r kill -9 2>/dev/null
pgrep -f "server.py" 2>/dev/null | xargs -r kill -9 2>/dev/null
.venv/bin/python server.py >/tmp/taki-server.log 2>&1 &
sleep 2 && curl -s http://localhost:5001/api/status
```
Open http://localhost:5001 in the browser.

## Project shape — 5-agent cascade, 4 modes

```
Bright Data live web → SharedBundle (Lean cache)
        ↓ PII redact → leak/scope guard
        ↓ (parallel fan-out)
[Marketing] [GTM] [Finance] [Security]   ← 4 dept agents
        ↓ grounding (drop uncited claims)
        ↓ cross-pollinate (synergies + handoffs)
        ↓ Strategy (Chief of Staff synthesizes StrategicPlan)
        ↓ assemble → CascadeBrief
        ↓ /api/run SSE → cytoscape graph + dashboard re-render
```

| Mode | Trigger | Subject |
|---|---|---|
| self (V7)   | 🚀 analyze my business modal | the founder's OWN site + competitor URLs |
| target      | ⚡ live run popover         | someone else's account (sales intel) |
| demo        | ▶ live demo button          | fixture Northwind cascade through real backend |
| replay      | ▶ replay cascade            | scripted animation of cached brief.json |

## Recent state (chronological commits — most recent at the bottom)

- 4fa9955 V1.1 identity reset — inline 3-stream 滝 SVG + warm-ink palette
- 61b3019 V3 cytoscape cascade graph
- 47ab3ec V2 LangGraph backend (StateGraph + per-node event stream)
- c687915 V3.2 replay-cascade mode
- 5b49b94 V4 UX polish — confidence bars + dropped-claims drawer + a11y
- 5cf35d3 demo: one-command boot + `run.py --demo` + README quickstart
- aec25eb V5 live mode (Flask + SSE) + edge-label clarity fix
- b2470a3 V6 Strategy department (Chief of Staff) + StrategicPlan hero
- 110733e V7 SMB pivot — Marketing dept + self-mode + onboarding form
- 6fc98b6 V7.1-V7.4 — 4-col layout + self-mode resilience + observable status
- 8ede64a V7.6-V7.8 — URL audit (normalize + DNS) + post-scrape quality gate
- V7.10 — Pydantic auto-coerce singleton → list (fixed the ValidationError × 4
  on real Orchid SRL self-mode run where the LLM returned bare dicts instead
  of one-element lists for MarketingSignal fields)
- V7.11-V7.13 (just shipped) — depth-over-surface prompts (Marketing +
  Strategy are now industry-aware; high-barrier B2B bias toward proof-of-
  execution + named collaborators + certifications, not SEO/copy/voice);
  V7.12 auto-discovers concept-grouped sub-pages on the founder's domain
  (about / projects / references / products / certifications / news +
  synonyms — first per concept group wins) so depth pages reach the
  cascade instead of homepage-only; docs/JOURNEY.md judge-friendly
  narrative; README gains 'How Taki maps to all three Bright Data Tracks'
  section.

## Tests
- 117/117 green (~14s)
- tests/test_schema_coercion.py — V7.10 Orchid SRL regression
- tests/test_url_audit.py — normalize / DNS / audit_urls / quality gate
- tests/test_subpage_expansion.py — V7.12 sub-page discovery synonyms

## Known issues / queued enhancements

| Tier | Item | Why deferred |
|---|---|---|
| viz | per-dept inline graphs (positioning quadrant, compliance scorecard) | substantial SVG/D3 work |
| viz | competitor mind-map (user center, competitors as satellites) | needs second cytoscape canvas + layout |
| audit | LLM-mediated typo guess on dropped URLs | hallucination risk — needs web-search verification step |
| audit | per-URL industry-relevance check | +1 LLM call × URLs (~$0.001 each, +3s latency) — add as opt-in toggle |
| interact | on-demand "tell me more about competitor X" deep-dive | new sub-cascade design |
| copy | LLM-generated homepage / pricing-page suggestions | new agent + UI surface |
| ops | continuous monitoring (weekly re-scan with delta diff) | scheduler + state diff |
| ops | CRM export (Salesforce / HubSpot push) | integration layer |
| ops | submit to lablab.ai + record 5-min video | hackathon submission |

## Quick file map

```
agents/
  schemas.py          # Pydantic — _AutoListBase mixin auto-wraps singletons → lists
  base.py             # build_context, parse_into, GROUNDING_RULE
  marketing.py        # V7 — 4th dept · self/target prompt variants
  gtm.py · finance.py · security.py
  strategy.py         # V6 Chief of Staff — self/target prompt variants
  orchestrator.py     # build_cascade_brief delegates to cascade_graph
  cascade_graph.py    # LangGraph StateGraph: pii→leak→4 depts→grounding
                      #   →cross_pollinate→strategy→assemble
guardrails/
  pii.py · leak.py · grounding.py
services/
  brightdata.py       # build_bundle (target) + build_self_bundle (per-URL skip + quality gate)
  url_audit.py        # V7.6 normalize_url + dns_resolves + audit_urls + is_low_quality
  cache.py            # data/<slug>/bundle.json + brief.json + events.jsonl
  llm.py              # Vertex via ADC (preferred) or Gemini AI Studio
frontend/
  index.html          # warm-ink editorial layout, 3-button toolbar + analyze-my-business modal
  app.js              # render() + status banner + onboarding form wiring
  cascade-flow.js     # cytoscape graph + replay + SSE handlers
  brief.json          # cached Vercel target-mode brief (with hand-crafted plan + marketing)
server.py             # Flask + flask-cors — /, /api/status, /api/run (SSE)
run.py                # CLI: --demo (fixture) | "Target" url:type ... (live)
demo.sh               # boot venv + deps + tests + server + browser
fixtures/
  sample.py           # Northwind Analytics — 8 subject-tagged sources
  fake_llm.py         # fake_{gtm,finance,marketing,security,strategy}_llm
tests/                # 117 tests — incl. test_schema_coercion + test_subpage_expansion + test_url_audit
docs/JOURNEY.md       # ⭐ judge-facing narrative (V7.13): problem → architecture
                      #   → 3-track mapping → V1-V7.13 build log → lessons → roadmap
docs/
  STATUS.md           # per-session build log
  RESUME.md           # this file
  PRESENTATION.md     # lablab form text + 5-min video script + slide outline
  HANDOFF.md          # original morning handoff (V1-V5 era)
```

## Live env
- Vertex AI via ADC at ~/.config/gcloud/adc_taki.json
  (project project-2be42b84-14e0-421a-b3a)
- Bright Data Unlocker zone taci_unlocker
- `.env` filled (BRIGHTDATA_API_KEY + GCP_PROJECT_ID)
- langgraph 0.2 · flask 3 · pydantic 2 · cytoscape+GSAP via CDN

## Useful commands
```bash
.venv/bin/python -m pytest -q                 # full suite (117 in ~14s)
.venv/bin/python run.py --demo                # generate Northwind brief offline
.venv/bin/python run.py "Stripe" \
    https://stripe.com/pricing:pricing \
    https://stripe.com/jobs:jobs              # target-mode CLI live run
.venv/bin/python server.py                    # Flask backend on :5001
./demo.sh                                     # one-command bootstrap
git log --oneline | head -15                  # recent commits
```

## Discipline
- Ultraplan style — ONE step at a time, build → test → commit per session.
- Karpathy rules (from ~/.claude/CLAUDE.md): simplicity first, surgical
  changes, goal-driven, think before coding.
- Caveman compression on by default — terse prose, normal code/commits.
- Don't drift back into Diligence territory (SEC filings, bull/bear) —
  this is BD live-web + dept-cascade.

## What you should NOT do
- No SA-key creation (Vertex via ADC only).
- No public deploy of server.py — no auth, would let strangers spend
  Bright Data credit. Static frontend/ deploys fine to Vercel.
- No silent LLM "did you mean ___?" typo correction (hallucination risk).
```
