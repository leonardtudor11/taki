# Taki — Resume prompt (V7.40 state · 2026-05-28)

Paste everything inside the fence below into the **first message** of a
fresh Claude Code session. The prompt is self-contained — locates the
repo, names current state, and lists the remaining polish work before
the 2026-05-30 hackathon deadline.

---

```
You are resuming work on **Taki** — agentic-enterprise-on-live-web-data,
built for Bright Data "Web Data UNLOCKED" 2026 (deadline 2026-05-30).
Repo at /Users/mirel-leonardtudor/taki. Stay strictly inside that
directory.

## Boundary (security)
- Read/write/run only inside /Users/mirel-leonardtudor/taki.
- No personal files, no other projects, no ~/.env, no SA keys (Vertex ADC only).
- Cloud Run + Vercel auth token lives in .env (gitignored). Never commit it.
- Every session ends in a git commit.

## Sanity boot
```bash
cd ~/taki
.venv/bin/python -m pytest -q --ignore=tests/test_cascade_brief.py --ignore=tests/test_server.py
# expect: 219 passed (test_server.py has 5 preexisting auth-leak failures
# unrelated to features — TAKI_AUTH_TOKEN leaks from .env into test env)
```

## What is LIVE end-to-end (V7.40)
- Repo:        https://github.com/leonardtudor11/taki (MIT, public)
- Dashboard:   https://frontend-sage-pi.vercel.app (Vercel, alias)
- Backend:     https://taki-backend-xmkvqnh62a-uc.a.run.app (Cloud Run us-central1)
- Auth:        TAKI_AUTH_TOKEN in .env + Cloud Run Secret Manager
- Share URL:   https://frontend-sage-pi.vercel.app/?key=<TAKI_AUTH_TOKEN>
- Gallery:     ?case=orchid | supabase | notion | pfizer

The 🚀 "analyze my business" button on the dashboard hits the Cloud Run
backend cross-origin (api.json indirection) and streams cascade events
back via SSE. Backend is bearer-token gated. Auth + spend tracker
prevent drive-by traffic from draining BD + Vertex credit.

## Pipeline (V7.40 — 13 LLM agents + 1 post-cascade enrichment)
```
URL audit (normalize_url + dns_resolves)
    ↓
Bright Data live web
  ├── V7.22 SERP external discovery (Web Unlocker against google.com)
  ├── V7.33 academic overlay (Scholar + SemSch + PubMed/arXiv/SSRN/IEA-IRENA per sector)
  ├── V7.33 analyst overlay (Gartner / Forrester / HN / Reddit / LinkedIn pulse / podcasts)
  └── V7.36 LLM-generated industry queries (when industry hint passed)
    ↓ tier classifier (T1 regulator → T6 review, BLOCKED filtered)
build_bundle:
  ├── V7.30 chrome detection + Wikipedia/Wayback fallback per URL
  ├── V7.31 sub-page concept walk (about/team/pricing/careers/investors/
  │        research/blog/projects/references/products/certifications/news)
  └── SharedBundle (Lean — scrape once, all agents read)
    ↓ PII redact → leak filter (trusted-publisher exempt)
    ↓ (parallel — 4 dept agents w/ injectable LLMs)
[Marketing] [GTM] [Finance] [Security]
    ↓ grounding (claim-level + V7.21 cite-level)
    ↓ V7.35 LLM cross_pollinate (per-company handoffs + synergies,
    │       hallucinated-URL filter; templated fallback if LLM fails)
    ↓ profile_extract (LLM extracts industry/stage/competitor_names)
    ↓ V7.34 expert_quotes_pass (LLM extracts verbatim attributed quotes)
    ↓ sector_pass (one of pharma/saas/energy/generic — typed sub-pipeline)
    ↓ (parallel — 5 reasoning agents)
[Strategy] [Contradictions] [Porter] [SWOT] [PESTLE]
    ↓ assemble → CascadeBrief
    │     + V7.37 BundleStats (tier/subject/type breakdown,
    │       sub-page hits, chrome fallbacks, expert_quote count)
    ↓ (post-cascade, server.py + run.py)
    │ V7.38 competitor_summary: SERP+Unlock+LLM per competitor
    │       (max 3, ~$0.15 spend cap, soft-fail per entry)
    ↓ SSE event stream → cytoscape graph + dashboard re-render
```

## Key invariants (V7.29-pt3 + V7.35 hard-won)
- LLM retry: 4× exponential backoff on Exception OR empty response.
  Wrapped at services/llm.py — every agent benefits transparently.
- _AutoListBase coerces None→"" for str fields + singleton→list.
- LangGraph fan-in requires equal-depth branches; 5-way fan from
  sector_pass into assemble stays equal-depth. New V7.34 expert_quotes
  + V7.35 cross_pollinate inserted SERIALLY (not parallel) to preserve
  this guarantee — Vertex degrades responses on >5-way fan-out.
- Sector signal: exactly one of pharma_signal / saas_signal /
  energy_signal / generic_signal populated per brief.
- LLM cross_pollinate (V7.35): refs URLs filtered against the claim
  URLs the LLM was shown. URL hallucination defense.
- Cytoscape (V7.39): target-distance-from-node=0, arrow-scale=1.6,
  endpoint=outside-to-node, arc distances -32/-58/-84 — arrows plug
  cleanly into node borders.

## All RESUME thoroughness gaps CLOSED in V7.30-V7.40
- ✅ #1 sub-page discovery        → V7.31 (10 concept groups)
- ✅ #2 JS chrome fallback         → V7.30 (Wikipedia + Wayback)
- ✅ #3 competitor cascade         → V7.38 (lightweight per-competitor mini)
- ✅ #4 expert quotes              → V7.34 (agent + frontend panel)
- ✅ #5 academic depth             → V7.33 (Scholar/SemSch/PubMed/arXiv/SSRN)
- ✅ #6 analyst commentary         → V7.33 (Gartner/HN/LinkedIn/podcasts)
- ✅ #7 frontend renders           → V7.34 / V7.37 / V7.38 panels shipped
- ✅ (visual) graph differentiation → V7.32 (per-case dept counts)
- ✅ (visual) arrow disconnect      → V7.39 (distance=0, arrow-scale=1.6)
- ✅ (visual) graph aesthetics      → V7.40 (cut-rect source, SHU-glow brief, sector edges subordinate)
- ✅ (intel) templated handoffs    → V7.35 (LLM-driven per-cascade)
- ✅ (intel) industry coverage     → V7.36 (LLM SERP queries any industry)
- ✅ (audit) trust signal          → V7.37 (BundleStats strip)
- ⏸  #8 cached brief reruns        → USER decision (cost ~$1/case)

## What's left for video demo
1. Pick one NEW target outside the gallery, fire a live dashboard run
   with industry hint filled, screen-record the SSE stream + final brief.
2. (optional) Refresh gallery briefs via CLI w/ industry hints:
     .venv/bin/python run.py "Pfizer" \
       https://www.pfizer.com/:site https://investors.pfizer.com/:site \
       --industry "branded prescription pharmaceuticals" --region US \
       --stage scale --no-cache
   then `cp frontend/brief.json frontend/briefs/pfizer.json` + redeploy
   frontend.
3. (optional) Loosen V7.34 expert_quotes prompt if 0-quote pattern
   recurs (current prompt is strict on verbatim-in-quotes attribution).
4. (optional) Fix preexisting test_server.py auth-leak (monkeypatch
   server._AUTH_TOKEN="" in client fixture).

## Deploy commands (idempotent)
- Backend:    `bash scripts/deploy_cloudrun.sh`
- Frontend:   `cd frontend && npx vercel --prod --yes`
- New target via CLI (V7.41 full parity w/ dashboard):
              `.venv/bin/python run.py "Company" https://co.com:site \
                --industry "..." --region US --stage growth [--no-cache]`
- OG image:   `.venv/bin/python scripts/gen_og.py`

## Tests
- 219/219 green excl. test_cascade_brief.py (e2e, +6 min) and 5
  preexisting test_server.py auth-leak failures (orthogonal).
- Full suite ~6s on macOS for unit + integration.
- Schema coercion: tests/test_schemas.py, test_schema_coercion.py
- Cascade: tests/test_cascade_graph.py, test_strategy.py
- Self-mode regression: tests/test_self_mode.py
- BD templates: tests/test_brightdata.py
- V7.30 JS chrome: tests/test_js_chrome_fallback.py (14 cases)
- V7.31 target sub-page: tests/test_target_subpage_discovery.py (13)
- V7.34 expert quotes: tests/test_expert_quotes.py (10)
- V7.35 LLM cross_pollinate: tests/test_cross_pollinate_llm.py (7)
- V7.36 query generator: tests/test_query_generator.py (11)
- V7.37 bundle stats: tests/test_bundle_stats.py (8)
- V7.38 competitor summary: tests/test_competitor_summary.py (9)

## File map (where to look for what)
- agents/cascade_graph.py        — LangGraph topology (V7.35 cross_pollinate
                                   inside cross_node, V7.34 expert_quotes_pass,
                                   V7.37 _compute_bundle_stats)
- agents/{gtm,finance,security,marketing}.py — 4 dept agents
- agents/strategy.py             — Strategy w/ _SECTOR_GUIDE constant (V7.28)
- agents/profile.py              — target-mode profile extractor (V7.28)
- agents/sector.py               — pharma/saas/energy/generic (V7.29)
- agents/{porter,swot,pestle,contradictions}.py — universal frameworks
- agents/cross_pollinate_llm.py  — V7.35 LLM cross-pollination
- agents/expert_quotes.py        — V7.34 verbatim quote extractor
- agents/query_generator.py      — V7.36 LLM-generated industry SERP
- agents/competitor_summary.py   — V7.38 post-cascade competitor mini-bundle
- agents/schemas.py              — every Pydantic schema (~700 lines)
- guardrails/{pii,leak,grounding}.py — three-layer guardrail
- services/brightdata.py         — tier classifier + SERP templates +
                                   V7.30 chrome + V7.31 discover_subpages +
                                   V7.33 academic_queries + analyst_queries
- services/llm.py                — Vertex/AI-Studio + V7.29-pt3 retry wrap
- frontend/app.js                — dashboard render (renderBundleStats,
                                   renderExpertQuotes, renderCompetitorSummaries,
                                   renderSectorSignal, …)
- frontend/cascade-flow.js       — cytoscape graph + SSE adapter
                                   (V7.32 dept counts, V7.39 arrow fix,
                                   V7.40 source/brief shape distinction)
- frontend/{cases.json,api.json,brief.json,briefs/*.json}
                                  — gallery index + backend config + cached briefs
- scripts/deploy_cloudrun.sh     — backend deploy (handles IAM + secrets)
- scripts/rerun_briefs.py        — refresh briefs w/o BD spend (LLM-only)
- run.py                         — CLI entry (V7.41 full parity w/ dashboard)
- server.py                      — Flask SSE backend
- docs/PRESENTATION.md           — video script + lablab form text
- docs/ARCHITECTURE.md           — deep technical reference
- docs/STATUS.md                 — per-session checkpoint log
```
