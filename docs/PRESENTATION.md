# Taki — Submission package

lablab.ai form text, 5-min video script, and slide deck outline for the Bright Data
**Web Data UNLOCKED** 2026 hackathon. Paste, record, ship.

Current state: V7.26 · 9-agent cascade · 14 LangGraph nodes · 150/150 tests green ·
live frontend: `https://frontend-sage-pi.vercel.app` (Orchid SRL self-mode brief,
79 cites / 8 domains, 0 hallucinations).

---

## 1. lablab.ai form fields

### Project title
**Taki — agentic enterprise on live web data**

### Short description (≤ 200 characters)
> Nine AI agents — four departments + a strategist + Porter/SWOT/PESTLE/Contradictions — share one Bright Data live-web cache and cascade into a grounded enterprise brief.

### Long description
> Most "AI for revenue" tools are a single LLM with a single feed. Real enterprise decisions are cross-functional — Sales, Finance, Marketing and GRC look at the same target through different lenses, *then* a strategist reconciles them through structured frameworks (Porter, SWOT, PESTLE, contradiction analysis).
>
> **Taki models that.** For a target account, four department agents — GTM, Finance, Marketing, Security — read one shared Bright Data live-web bundle (scrape once, the Lean way) and each produce a structured intelligence object. A grounding guard drops any claim — and any citation — that doesn't map to a snippet that actually exists in the bundle. A cross-pollination pass writes explicit dept-to-dept handoffs and synergies ("Finance → GTM: pricing changed, adjust timing"). Then five reasoning agents run in parallel on the grounded base: a Strategist produces a prioritized play list with a Gantt timeline; Porter's Five Forces, SWOT, and PESTLE produce framework grids; a Contradictions agent surfaces opposing-source claim pairs and rates severity. Everything joins into a single `CascadeBrief` an enterprise team can act on.
>
> **Bright Data is central.** A source-tier classifier ranks every fetched URL — T1 regulators (gov, IEA, IRENA, SEC), T2 academic (Nature, arXiv, Scholar), T3 news/analyst (FT, Bloomberg, Reuters, Gartner), T4 trade press, T5 community (capped at 30%), T6 reviews (capped), BLOCKED (Facebook/Instagram/TikTok/raw blogs are weight 0). Industry-aware SERP queries are layered automatically — wind/solar/SaaS/biotech/fintech each get tailored discovery templates. A spend tracker enforces a configurable cap so an unattended run can't blow the credit. Without Bright Data's SERP + Web Unlocker, none of these live signals — competitor pricing today, this morning's job posts, current regulatory rulings — are reachable.
>
> Built with hard guardrails (PII redaction, leak/scope withhold with trusted-publisher exemption, claim-level *and* citation-level grounding) so the system is something an enterprise GRC team would let into production.

### Tracks
- **Primary:** Track 1 — GTM Intelligence
- Integrates: Track 2 (Finance & Market) + Track 3 (Security & Compliance) + frameworks reasoning layer

### Technology tags
`Bright Data` · `Python` · `LangGraph` · `Pydantic` · `Vertex AI / Gemini` · `Multi-agent` · `Static HTML/JS` · `ECharts + Cytoscape` · `AI guardrails` · `Enterprise AI`

### Bright Data usage statement (required)
> Taki uses Bright Data as its sole live web data layer. The pipeline calls Bright Data's SERP zone (industry-aware queries: regulators + filings + Reuters/FT/Bloomberg + scholar + industry-specific layers for wind/solar/SaaS/biotech/fintech/etc.) and Web Unlocker zone (per-URL bypass on competitor pricing, careers, news, reviews, regulator filings). Every fetched URL passes a **source-tier classifier** (T1 regulator 1.00 weight → T6 review 0.50 → BLOCKED 0 weight) before its content is allowed into the shared `SharedBundle` cache that every agent consumes. A SpendTracker enforces a configurable cap (`TAKI_BD_SPEND_CAP`) so an unattended run cannot exceed the allocated credit. Zones and limits are read from `.env`. Without Bright Data, none of the live signals are reachable in real time — the live-web layer is what makes the product possible.

### Cover image (16:9 PNG/JPG)
**Spec** — dark background (~#0b0f17). Two horizontal rows under the title `Taki 滝` in white:
- Top row: four department badges (GTM cyan · Finance green · Marketing magenta · Security amber)
- Bottom row: four framework badges (Porter / SWOT / PESTLE / Contradictions)
- Center: arrows converging into a `★ CascadeBrief` badge
- Bottom strip: `live web · grounded · enterprise-ready`

Generate via Figma / Canva / image-gen — paste spec verbatim.

### Demo URL
`https://frontend-sage-pi.vercel.app`  (cached Orchid SRL brief — wind energy + Romania)

### GitHub URL
`https://github.com/leonardtudor11/taki`  (MIT)

### Video URL placeholder
(YouTube/Vimeo unlisted link after recording)

---

## 2. Video script (≤ 5 min)

Screen-share + voice-over. Record in OBS / QuickTime → MP4.

**Pre-record boot:** `./demo.sh` opens `http://localhost:5001` with the bundled
Orchid SRL brief.

### Scene 1 — Hook (0:00–0:25)
> "Most 'AI for revenue' is one LLM staring at one feed. Real companies don't work that way. Sales, Finance, Marketing and GRC look at the same account through different lenses — *then* a strategist reconciles them through structured frameworks. **Taki** — Japanese for cascade — models that."
>
> [Visual: open dashboard. Wordmark `taki 滝 · cascading intelligence`. Camera pans across the four department panels.]

### Scene 2 — Watch the cascade think (0:25–1:50)
> "One target. Four department agents share ONE live Bright Data bundle — scraped once, consumed by everyone. That's the Lean principle."
>
> [Click **▶ replay cascade**. Narrate as the 14 LangGraph nodes animate:]
>
> "PII redaction first — emails and phones scrubbed before any LLM sees them. Leak guard next — confidential content withheld, but trusted publishers like Reuters and Bloomberg are exempt from the keyword scan so legitimate news isn't false-flagged. Parallel fan-out: GTM, Finance, Marketing, Security all read the same clean bundle simultaneously. Each emits structured claims. The grounding guard joins — every claim must cite a snippet that actually exists in the bundle; *and* every citation must map back to a real source. Eight claims drop. Now cross-pollination: Finance → GTM 'pricing changed, adjust timing.' Security → GTM 'reputational signal, frame responsibly.' Real cross-department reasoning, written down. Then five agents run in parallel on the grounded base: a Strategist, Porter's Five Forces, SWOT, PESTLE, and a Contradictions detector that finds opposing-source claim pairs. Everything joins. One unified Cascade Brief."

### Scene 3 — Interact (1:50–2:40)
> [Click the **GTM node** in the cascade graph. Other panels fade.]
>
> "Click a department or framework — the rest fade. The graph is the lens." [Click empty space; click **Security**.] "Security view — exposure indicators, reputational signals, third-party risk. Every claim has a citation chip linking to the live source URL."
>
> [Hover a curved handoff edge. Tooltip strip reveals full message.] "Hover an edge — full handoff text. Cross-functional reasoning, made visible."

### Scene 3.5 — Frameworks & the plan (2:40–3:35)
> [Scroll to Strategic plan hero.] "Here's what no other 'AI for sales' tool gives you: not signals — a *plan*. The Strategist reads everything and synthesizes: ICP fit, deal size range, urgency window, five prioritized plays each with a dept owner, a timeframe, and a citation back to the evidence. The Gantt strip below shows when each play runs."
>
> [Scroll to Porter radar.] "Porter's Five Forces — rivalry 5, buyer power 4, substitutes 4. The radar makes the pressure pattern obvious."
>
> [Scroll to SWOT 2×2 and PESTLE.] "SWOT 2×2 with impact ratings. PESTLE macro factors — political 5↑, environmental 5↑ — because for a wind-energy company in Romania, the EU Green Deal is a tailwind, not background noise."
>
> [Scroll to Contradictions panel.] "And contradictions — opposing-source claim pairs ranked by severity. Here: the WindEnergy Hamburg 2026 exhibitor list mismatches the company's own press release. Severity 3 of 3. Worth a phone call before the meeting."

### Scene 4 — Guardrails are the enterprise unlock (3:35–4:15)
> [Click the **"Hallucinations caught — N ungrounded claims dropped"** drawer.]
>
> "The grounding guard caught and dropped these *before* they reached the brief. Two layers: claim-level (the assertion must cite a real snippet) and citation-level (the citation URL must map back to a fetched source). If either fails — gone. Not flagged — gone."
>
> [Point at guardrail badge row.] "PII redacted, sources withheld, ungrounded dropped. The brief is honestly marked 'grounded: yes' only when every survivor passes both layers. That's the integrity an enterprise GRC team needs."

### Scene 5 — Bright Data + close (4:15–5:00)
> "None of this works without Bright Data. Industry-aware SERP queries — for Orchid SRL the system layers wind-energy templates onto the base regulator + filings + analyst stack. Web Unlocker pulls every page past bot blocking. Every URL hits a source-tier classifier — T1 regulators like IRENA and IEA get full weight, T5 community capped at 30%, raw blogs blocked outright. Spend cap enforced — an unattended run can never burn the credit."
>
> [Brief switch to terminal: `cat agents/cascade_graph.py | head -40` showing the 14-node `langgraph.StateGraph`.]
>
> "Real LangGraph under the hood — 14 nodes, explicit parallel fan-out, every node emits an SSE event so the cascade is fully traceable. Same architecture metaphor as how a real enterprise actually works — departments, cross-talk, compliance auditing everyone, a strategist reconciling through frameworks. One shared data layer, Bright Data. One unified deliverable."
>
> "Taki."
>
> [Cut to README architecture diagram, hold 3s. Fade.]

---

## 3. Slide deck outline (8 slides, PDF)

Build in Keynote / Slides → export PDF.

| # | Slide | Key content |
|---|---|---|
| 1 | **Title** | "Taki 滝 — agentic enterprise on live web data" · Mirel Leonard Tudor · Bright Data Web Data UNLOCKED 2026 |
| 2 | **The problem** | "Enterprise decisions are cross-functional + framework-driven. Tools are not." Four lenses + four frameworks on the same account, siloed today |
| 3 | **The idea** | 9 agents · 4 departments + Strategist + Porter/SWOT/PESTLE/Contradictions. ONE shared Bright Data cache. Cascade → grounding → cross-talk → frameworks |
| 4 | **Architecture** | ASCII diagram (14 LangGraph nodes). Highlight: scrape-once · guardrails-before-LLM · grounding-after-LLM · frameworks-after-grounding |
| 5 | **Bright Data is central** | SERP industry-aware + Web Unlocker + source-tier classifier (T1→T6→BLOCKED) + spend cap. Without BD: no live signals |
| 6 | **Guardrails** | PII redaction · leak withhold (trusted-publisher exempt) · claim-level + citation-level grounding. Concrete: N hallucinations caught on the Orchid run |
| 7 | **Demo screenshot** | Live dashboard: dept panels + cascade flow + Porter radar + SWOT 2×2 + PESTLE + Gantt + contradictions + guardrail badges |
| 8 | **Business value + ask** | Enterprise-ready (grounded, audited, framework-driven). Cached Orchid SRL + Supabase briefs ship in repo. Future: more depts, real-time alerts. Repo + demo links |

---

## 4. Final pre-submit checklist

- [ ] `.env` filled (BRIGHTDATA_API_KEY, SERP_ZONE, UNLOCKER_ZONE, GCP_PROJECT_ID/GEMINI_API_KEY, TAKI_BD_SPEND_CAP)
- [ ] `python run.py "Real Company" url:pricing url:jobs` ran ≥ 2 real accounts; cached briefs refreshed in `data/<slug>/`
- [ ] `./demo.sh` boots on `:5001`; **150/150 tests pass** (`.venv/bin/python -m pytest -q`)
- [ ] Dashboard renders: cytoscape 14-node graph · 4 dept panels · Porter radar · SWOT 2×2 · PESTLE · Gantt · contradictions panel · ▶ replay animates · click-node filters · dropped drawer expands
- [ ] Frontend deployed: `cd frontend && npx vercel --prod --yes` (auto-deploy broken — see RESUME.md). Live URL captured
- [ ] Repo pushed public to `github.com/leonardtudor11/taki` (already public, MIT)
- [ ] Video recorded (≤ 5 min MP4) → unlisted YouTube
- [ ] Slides exported to PDF (8 slides)
- [ ] Cover image rendered (16:9, dept + framework rows)
- [ ] lablab form: paste fields above, attach cover/slides/video/repo/demo URLs
- [ ] Submit ✅

## 5. Demo record fail-safes

If a live re-record is needed during the deadline crunch:
- `./demo.sh` is idempotent — re-running reuses the existing server.
- Dashboard works offline once `frontend/brief.json` is checked in (it is — Orchid SRL).
- If `brief.json` is overwritten by mistake: `git checkout frontend/brief.json` restores the Vercel-cached Orchid run.
- The ▶ replay button drives the entire 14-node cascade animation from `brief.json` alone — no backend run needed during recording.
- Backup cached brief: `data/supabase/brief.json` (SaaS / BaaS angle) — swap into `frontend/brief.json` if Orchid is mid-edit.
- If Vertex 429 rate-limits mid live-demo recording: wait 90s, re-shoot Scene 2. Don't restart immediately.
