# Taki — Resume prompt (V7.29 state · 2026-05-28)

Paste everything inside the fence below into the **first message** of a
fresh Claude Code session. The prompt is self-contained — locates the
repo, names current state, lists the prioritized work to close the
"thoroughness gap" before the 2026-05-30 hackathon deadline.

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
.venv/bin/python -m pytest -q --ignore=tests/test_cascade_brief.py  # ~8 min, 146/146
```

## What is LIVE end-to-end (V7.29)
- Repo:        https://github.com/leonardtudor11/taki (MIT)
- Dashboard:   https://frontend-sage-pi.vercel.app (Vercel)
- Backend:     https://taki-backend-xmkvqnh62a-uc.a.run.app (Cloud Run, us-central1)
- Auth:        TAKI_AUTH_TOKEN in .env + Cloud Run Secret Manager
- Share URL:   https://frontend-sage-pi.vercel.app/?key=<TAKI_AUTH_TOKEN>
- Gallery:     ?case=orchid | supabase | notion | pfizer

The 🚀 "analyze my business" button on the dashboard hits the Cloud Run
backend cross-origin (api.json indirection) and streams cascade events
back via SSE. Backend is bearer-token gated.

## Pipeline (V7.29 — 11 agents, sector-conditional)
```
Bright Data live web (SERP discovery + Web Unlocker)
                  ↓ tier classifier (T1 regulator → T6 review, BLOCKED filtered)
            SharedBundle (Lean — scrape once, all agents read)
                  ↓ PII redact → leak filter (trusted-publisher exempt)
                  ↓ (parallel — 4 dept agents)
        [Marketing] [GTM] [Finance] [Security]
                  ↓ grounding (claim + V7.21 cite-level)
                  ↓ cross_pollinate (handoffs + synergies)
                  ↓ profile_extract (LLM extracts industry/stage/competitor_names)
                  ↓ sector_pass (one of pharma/saas/energy/generic — typed sub-pipeline)
                  ↓ (parallel — 5 reasoning agents)
        [Strategy] [Contradictions] [Porter] [SWOT] [PESTLE]
                  ↓ assemble → CascadeBrief
                  ↓ SSE event stream → cytoscape graph + dashboard re-render
```

## Key invariants (V7.29-pt3 hard-won)
- LLM retry: 4× exponential backoff on Exception OR empty response.
  Wrapped at services/llm.py — every agent benefits transparently.
- _AutoListBase coerces None→"" for str fields + singleton→list. Without
  this, LLM-emitted null in any nested item collapsed the whole signal.
- LangGraph fan-in requires equal-depth branches; mismatched depths fire
  assemble twice. The V7.29 topology is profile_extract → sector_pass →
  {strategy + 4 frameworks} so all 5 reasoning agents are equal depth.
- Sector signal: exactly one of pharma_signal / saas_signal /
  energy_signal / generic_signal is populated per brief — derived from
  business_profile.industry via classify_sector().
- Frontend cytoscape: 6-node base + sector satellite cluster (3 nodes
  per active sector) at y=360. Positions preset in
  cascade-flow.js:presetPositions.

## THE THOROUGHNESS GAP — what's NEXT
Current state analyzes well WHEN the bundle is rich. When the bundle is
thin (3-4 sources, or page-chrome HTML from JS-rendered sites), depth
collapses. For ANY new non-mainstream firm to get a thorough cascade,
close these gaps. Prioritized by ROI:

### 1. Target-mode sub-page discovery (~2 hr, $0)
V7.12 added concept-grouped sub-page discovery (/about /projects
/references etc.) for SELF-mode only. Port to TARGET-mode so
`python run.py "Company" https://company.com` auto-expands to:
  /about, /team, /careers, /products, /pricing, /case-studies,
  /customers, /news, /press, /blog (latest 5), /investors,
  /research (sector-specific: /clinical-trials, /publications, etc.)
Reuse the existing services.brightdata.discover_subpages plumbing;
extend the concept group dictionary.
Files: services/brightdata.py, tests/test_subpage_expansion.py

### 2. JS-rendered site fallback (~1.5 hr, $0)
Symptom: Pfizer.com, Notion.so, and similar SPAs return page chrome
("Skip to main content / Sorry enable JavaScript") instead of body
content. Sector agent + dept agents starve.
Fix: detect chrome signature (text < 1500 chars OR matches
   pattern; trim "Skip to main content" boilerplate) and append
   fallback sources:
  (a) Wikipedia entry for the target name
  (b) archive.org wayback snapshot (most-recent)
  (c) Bright Data's JS-rendering Unlocker mode (verify zone setting)
File: services/brightdata.py:build_bundle + new helper.

### 3. Competitor cascade (~4 hr, ~$0.30 per cascade)
Today: competitors are mentioned in GTM signals + business_profile
.competitor_names but never deeply analyzed.
Add: for each named competitor (max 3), do a mini-bundle (3 pages each)
+ new agent "competitive_comparison" that outputs:
  - CompetitorComparison schema: pricing_axis, feature_axis,
    positioning_axis, customer_segment_axis, named entries per axis
    with citations.
Frontend: new panel rendering side-by-side comparison table.

### 4. Expert-quote extraction (~3 hr, $0)
Cascade has news/analyst sources but doesn't surface named-expert
quotes. New "expert_quotes" agent scans bundle for verbatim quotes
attributed to named individuals (CEO, analyst, regulator official,
academic researcher).
Schema: list[ExpertQuote{name, organization, quote, citation}].
Frontend: dedicated panel above departments.

### 5. Academic / journal depth (~1 hr, $0)
Today: base SERP layer has ONE scholar query. Expand to:
  - PubMed Central (life sci/health) — site:pmc.ncbi.nlm.nih.gov
  - arXiv (CS/ML/physics) — site:arxiv.org with industry-keyword overlay
  - SSRN (finance/legal/business) — site:ssrn.com
  - Semantic Scholar API (free tier, no key needed for basic)
  - Google Scholar tightened with date:2024..2026 filter
File: services/brightdata.py:default_external_queries + new academic
sub-helper.

### 6. Expert/analyst commentary depth (~2 hr, $0)
Add SERP queries for:
  - "{target}" Gartner OR Forrester OR IDC OR CB Insights
  - "{target}" HackerNews OR Reddit r/{relevant subreddit}
  - "{target}" LinkedIn analyst post
  - "{target}" podcast interview OR conference keynote
File: services/brightdata.py + per-industry overlay.

### 7. Frontend renders for new outputs (~3 hr, $0)
- CompetitorComparison panel (side-by-side table)
- ExpertQuotes section (blockquote cards w/ attribution)
- Academic papers row (filtered to high-tier sources)

### 8. Tests + cached-brief rerun (~1 hr + ~$0.45 spend)
- Fake LLMs for new agents in fixtures/fake_llm.py
- Tests for new agents + cascade integration
- Re-run Supabase + Notion + Pfizer + Orchid via scripts/rerun_briefs.py

**Suggested order**: 2 (Pfizer/Notion unblock) → 1 (depth from target's
own site) → 5+6 (richer external research) → 3 (competitor cascade) →
4 (expert quotes) → 7+8 (UX + tests).

## KNOWN GAPS in cached briefs as of 2026-05-28
- **Pfizer** sector_signal empty (0/0/0). Pfizer.com is JS-blocked at
  scrape time, returned navigation chrome only. Fix via gap #2 above
  or re-run with Wikipedia + science.pfizer.com/clinical-trials +
  investors.pfizer.com/sec-filings as seed URLs. Spend: ~$0.25.
- **Notion** sector_signal sparse (tiers=1, plg_metrics=1, logos=0).
  Same JS-block issue, smaller bundle. Same fix path.
- **Orchid** is self-mode → no sector field; brief still has full
  Porter/SWOT/PESTLE/contradictions. Used as default landing brief.
- **Supabase** is the clean demo — sector_signal populated 4/6/7,
  plays cited, all dept panels populated. Lead the video with it.

## Deploy commands (idempotent)
- Backend:    `bash scripts/deploy_cloudrun.sh`
- Frontend:   `cd frontend && npx vercel --prod --yes`
- Refresh cached briefs (LLM-only, no BD spend):
              `.venv/bin/python scripts/rerun_briefs.py`
- New target via CLI:
              `.venv/bin/python run.py "Company" https://co.com:site https://co.com/pricing:pricing`
- OG image:   `.venv/bin/python scripts/gen_og.py`

## Tests
- 146/146 green excl. test_cascade_brief.py (e2e, +6 min)
- Full suite ~12 min 12s on macOS
- Schema coercion: tests/test_schemas.py, test_schema_coercion.py
- Cascade: tests/test_cascade_graph.py, test_strategy.py
- Self-mode regression: tests/test_self_mode.py
- BD templates: tests/test_brightdata.py

## File map (where to look for what)
- agents/cascade_graph.py    — LangGraph topology (V7.29-pt3)
- agents/{gtm,finance,security,marketing}.py — 4 dept agents
- agents/strategy.py          — Strategy w/ _SECTOR_GUIDE constant (V7.28)
- agents/profile.py           — target-mode profile extractor (V7.28)
- agents/sector.py            — pharma/saas/energy/generic (V7.29)
- agents/{porter,swot,pestle,contradictions}.py — universal frameworks
- agents/schemas.py           — every Pydantic schema (~600 lines)
- guardrails/{pii,leak,grounding}.py — three-layer guardrail
- services/brightdata.py      — tier classifier + SERP templates
- services/llm.py             — Vertex/AI-Studio + V7.29-pt3 retry wrap
- frontend/app.js             — dashboard render (renderSectorSignal etc.)
- frontend/cascade-flow.js    — cytoscape graph + SSE adapter
- frontend/{cases.json,api.json} — gallery index + backend config
- scripts/deploy_cloudrun.sh  — backend deploy (handles IAM + secrets)
- scripts/rerun_briefs.py     — refresh briefs w/o BD spend
- scripts/gen_og.py           — OG image generator
- Dockerfile + .dockerignore  — Cloud Run container
- docs/PRESENTATION.md        — lablab form text + 5-min video script
- docs/ARCHITECTURE.md        — deep technical reference
- docs/JOURNEY.md             — design narrative

## Discipline
- Karpathy: surgical changes; minimum code; ASK before refactor.
- Caveman compression on (terse prose, normal code/commits).
- Vertex retry already at services/llm.py — don't add per-agent retry.
- Cache-bust ?v=X on app.js/cascade-flow.js. Bump when JS changes.
- LinkedIn + Stripe.com confirmed-blocked by BD Web Unlocker.
  Confirmed-good demo targets: Supabase, HashiCorp, Vercel, GitHub,
  Linear. JS-heavy sites (Pfizer, Notion) need fallback (gap #2).

## Hard-won knowledge (don't relearn)
- Vercel auto-deploy from GitHub broken since 2026-05-26. Use
  `npx vercel --prod --yes` from frontend/ for every frontend ship.
- Cloud Run runtime SA needs SIX roles (deploy_cloudrun.sh handles all):
  aiplatform.user, secretmanager.secretAccessor, storage.objectViewer,
  artifactregistry.writer, logging.logWriter, cloudbuild.builds.builder.
- LangGraph fan-in: equal-depth branches OR assemble fires twice.
- Pydantic str-fields reject null — _AutoListBase coerces None→"".
- Cytoscape preset layout: every node needs explicit position OR it
  lands at (0,0) (upper-left) and edges aim into empty space.
- Test "_cascade_brief.py" is the slow e2e (~6 min). Skip with
  --ignore=tests/test_cascade_brief.py during iteration.
- The bundle's "subject" field distinguishes TARGET vs COMPETITOR
  scrapes — used by profile + dept agents to attribute info correctly.
```

---

[end of fenced resume prompt — paste up to here, the body above it is for
the previous-session author, not the new session]

## Outside the fence — for the author (not the next session)

### Session-end commits worth knowing about
Most recent 8 commits, oldest first:
- `b454cca` (session start, V7.27 baseline)
- `65e3332` favicon + OG image + V7.21-V7.26 PRESENTATION.md refresh
- `4e1b8fb` README "Reviewing Taki — judge's fast path" section
- `a268916` Multi-brief gallery (Orchid · Supabase · Notion · Pfizer)
- `830c011` V7.28: sector-aware strategy prompts + citation fallback + profile extraction
- `8570fd5` V7.28: Cloud Run live (deploy_cloudrun.sh + bearer-token middleware)
- `0a2a41b` V7.28: refresh cached briefs w/ sector-aware prompts
- `552457c` V7.29: sector-conditional sub-pipeline (pharma/saas/energy/generic)
- `3fab425` V7.29-pt3: schema None-coercion + LLM-level retry wrap
- `0afb135` fix(cytoscape): position V7.29 sector satellite nodes (was 0,0)

### Why this resume prompt is the way it is
- Fenced block is what the new session reads — keeps context tight (~250 lines).
- Lists CURRENT-LIVE state + THOROUGHNESS GAPS + work order.
- Repeats discipline + hard-won knowledge so the new session doesn't
  re-learn Vercel-deploy-broken, LangGraph fan-in, Cytoscape positions.
- Calls out the spend cap + which targets are scrape-safe.
- Tells the next session what's RECOMMENDED order for thoroughness work.

### What was NOT done this session (queued for next)
- Sub-page discovery in target-mode (gap #1)
- JS-rendered site fallback (gap #2)
- Competitor cascade (gap #3)
- Expert-quote agent (gap #4)
- Academic depth expansion (gap #5)
- Expert/analyst commentary depth (gap #6)
- Frontend rendering for the above (gap #7)
- Re-running cached briefs for Pfizer + Notion with better seed URLs

### USER tasks still pending (lablab submission)
- Record 5-min MP4 demo (script in docs/PRESENTATION.md)
- Build 8-slide PDF (outline in PRESENTATION.md)
- 16:9 cover image (spec in PRESENTATION.md)
- Submit lablab.ai form (all field text drafted in PRESENTATION.md;
  demo URL = `https://frontend-sage-pi.vercel.app/?key=<token>`)
