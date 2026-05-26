# Taki — Submission package (draft)

Drafts for the lablab.ai form, the 5-min video, and the slide deck. Paste, record, ship.

---

## 1. lablab.ai form fields

### Project title
**Taki — agentic enterprise on live web data**

### Short description (≤ 200 characters)
> Three AI departments (GTM, Finance, Security) share one Bright Data live-web cache, cross-talk like a real company, and cascade into a single grounded revenue brief — with Compliance enforcing guardrails.

### Long description
> Most "AI for revenue" tools are a single LLM with a single feed. Real revenue decisions are cross-functional — Sales, Finance, and GRC look at the same target through different lenses and talk to each other.
>
> **Taki models that company.** For a target account, three department-agents — Revenue/GTM, Finance/Market, Security/Compliance — read one shared Bright Data live-web bundle (scrape once, the Lean way), each produce a structured intelligence object, then cross-pollinate via explicit dept-to-dept handoffs ("Finance → GTM: pricing changed, adjust timing"). A deterministic synergy pass combines signals no single department could see alone. The Security/Compliance department also audits the others: PII redaction, leak/scope withholding, and grounding (every claim must cite a snippet that exists in the bundle — uncited claims are dropped and logged). The result is a single grounded `CascadeBrief` an enterprise revenue team can act on.
>
> **Bright Data is central** — it's the live web data layer that makes the whole thing possible. Without continuously-updated, bot-bypassable web access, none of these signals (competitor pricing changes, hiring as alt-data, reputational shifts, regulatory moves) are available in real time. Taki wires Bright Data's SERP + Web Unlocker + Web Scraper zones behind a single shared cache that all three departments consume.
>
> Built with strict guardrails (no PII, no confidential content, no hallucinations) so the system is something an enterprise GRC team would actually let into production.

### Tracks
- **Primary:** Track 1 — GTM Intelligence
- Integrates: Track 2 (Finance & Market) + Track 3 (Security & Compliance) as feeder departments

### Technology tags
`Bright Data` · `Python` · `Pydantic` · `Gemini` · `Multi-agent` · `Next.js? no — static HTML/JS` · `Web scraping` · `AI guardrails` · `Enterprise AI`

### Bright Data usage statement (required)
> Taki uses Bright Data as its sole live web data layer. The pipeline calls Bright Data's SERP zone (for `target + pricing/careers/news` discovery) and Web Unlocker zone (for per-URL bypass on competitor pricing pages, careers pages, news, and review sites). All scraped content lands in a single shared `SharedBundle` cache that every department agent consumes (Lean: scrape once, no redundant pulls). A SpendTracker enforces a configurable cap so an unattended run cannot exceed the allocated credit. Spend cap and zones are read from `.env` (`BRIGHTDATA_API_KEY`, `BRIGHTDATA_SERP_ZONE`, `BRIGHTDATA_UNLOCKER_ZONE`, `TAKI_BD_SPEND_CAP`). Without Bright Data, none of the live signals (pricing changes today, this morning's job posts, current reputational chatter) are reachable — the live-web layer is what makes the product possible.

### Cover image (16:9 PNG/JPG)
**Spec** — dark background (~#0b0f17), three vertical columns labeled "GTM", "Finance", "Security" with department-color accents (cyan, green, amber), connected by arrows pointing into a central "★ CascadeBrief" badge, all under the title "Taki 滝" in white. Bottom strip: "live web · grounded · enterprise-ready". Generate via Figma, Canva, or an image-gen tool — paste the spec verbatim.

### Demo URL placeholder
`https://<your-vercel-url>.vercel.app`

### GitHub URL placeholder
`https://github.com/leonardtudor11/taki`

### Video URL placeholder
(YouTube/Vimeo unlisted link after recording S5.2)

---

## 2. Video script (≤ 5 min)

Format: screen-share + voice-over. Record in OBS / QuickTime. Export MP4.
Boot the dashboard once before recording: `./demo.sh` (opens `http://localhost:8000`
with the bundled real Vercel brief).

### Scene 1 — Hook (0:00–0:30)
> "Most 'AI for revenue' is one LLM staring at one feed. Real companies don't work that way. Sales, Finance, and GRC each look at the same account through different lenses — and they talk to each other. **Taki** — Japanese for cascade — models that."
>
> [Visual: the open dashboard. The three monoline streams in the logo draw down. Camera lingers on the wordmark — `taki 滝 · cascading intelligence`.]

### Scene 2 — Watch the cascade think (0:30–1:45)
> "One target. Three department agents share ONE live web data bundle — pulled via Bright Data, scraped once, consumed by everyone. That's the Lean principle."
>
> [Click **▶ replay cascade**. Narrate as it animates:]
>
> "PII redaction first — emails and phones scrubbed before any LLM sees them. Leak guard next — anything marked confidential is withheld. Now the parallel fan-out: GTM, Finance, Security all read the same clean bundle simultaneously. Each produces grounded claims. Grounding guard joins — eight uncited claims dropped before the brief. Now the cross-talk: Finance tells GTM 'pricing changed — adjust outreach timing.' Security tells GTM 'reputational signal — frame responsibly.' GTM tells Security 'hiring expansion — new attack surface.' Real cross-department communication. And the synergy pass — pricing increase plus support complaints — neither dept alone could say 'churn risk.' Together they do. Assemble. One unified Cascade Brief."

### Scene 3 — Interact (1:45–2:45)
> [Click the **GTM node** in the graph. Finance and Security panels fade. Only GTM's claims stay bright.]
>
> "Click a department, the other panels fade. The cascade graph is the lens." [Click empty space to clear, then click **Security**.] "Security view — exposure indicators, reputational signals, regulatory signals, third-party risk. Every claim has a citation chip that links to the live source URL."
>
> [Hover one of the curved handoff edges. Tooltip strip below the graph reveals the full message.] "Hover an edge — the full handoff text. Cross-functional reasoning, made visible."

### Scene 3.5 — The plan (the answer) (2:45–3:30)
> [Scroll to the top — Strategic plan hero section.] "And here's what no other 'AI for sales' tool gives you: not signals, a *plan*. The Chief of Staff agent reads everything the three departments produced and synthesizes it into a single executive plan. Headline: this is an enterprise-buy window. ICP fit: high, here's why. Deal size: $80-240k ARR, here's how I got there. Urgency: act this half — and here's the named reason. Five prioritized plays, each with a timeframe, a dept owner, and a citation back to the evidence." [Click into one play's citation.] "A CRO can hand this to a seller on Monday."

### Scene 4 — Guardrails are the enterprise unlock (3:30–4:15)
> [Click the red **"Hallucinations caught — 8 ungrounded claims dropped"** drawer to expand it.]
>
> "Eight LLM hallucinations the grounding guard caught and dropped before they could reach the brief. Every survivor must cite a snippet that actually appears in the scraped bundle — if it doesn't, it's gone. Not flagged — gone."
>
> [Point at the guardrail badge row.] "PII redacted, sources withheld, ungrounded dropped, grounded:no — because we caught hallucinations, the brief is honestly marked 'not fully grounded.' That's the integrity an enterprise GRC team needs."

### Scene 5 — Bright Data + close (4:15–5:00)
> "None of this works without Bright Data. The whole point: live, bot-bypassable, public web data, fresh — not last week's export. SERP zone discovers the sources, Web Unlocker pulls the pages past bot-blocking. One shared cache, every department reads it. Spend cap enforced — an unattended run can never burn the credit."
>
> [Brief switch to terminal: `cat agents/cascade_graph.py | head -30` showing the LangGraph topology + the `g.add_edge('leak_filter', 'gtm') / .add_edge('leak_filter', 'finance') / .add_edge('leak_filter', 'security')` lines.]
>
> "Real `langgraph.StateGraph` under the hood — explicit parallel fan-out, every node emits an event stream so the cascade is fully traceable. Same architecture metaphor as how a company actually works — departments, cross-talk, compliance auditing everyone. One shared data layer, Bright Data. One unified deliverable."
>
> "Taki."
>
> [Cut to README architecture diagram, hold 3 seconds. Fade.]

---

## 3. Slide deck outline (8 slides, PDF)

Build in Keynote / Slides, export PDF.

| # | Slide | Key content |
|---|---|---|
| 1 | **Title** | "Taki 滝 — agentic enterprise on live web data" · Mirel Leonard Tudor · Bright Data Web Data UNLOCKED 2026 |
| 2 | **The problem** | "Revenue decisions are cross-functional. Tools are not." 3 lenses on the same account (GTM/Finance/Security), siloed today |
| 3 | **The idea** | Departments as agents. ONE shared Bright Data cache. Cross-talk + cascade. Compliance audits everyone |
| 4 | **Architecture** | Paste the ASCII diagram from README; highlight: scrape-once, guardrails-before-LLM, grounding-after-LLM |
| 5 | **Bright Data is central** | SERP + Unlocker + Scraper zones, single shared cache, spend cap. Without BD: no live signals |
| 6 | **Guardrails** | PII redaction · leak/scope withhold · grounding (drop uncited claims). Concrete: planted hallucination caught in-flow |
| 7 | **Demo screenshot** | Live dashboard: dept panels + cascade flow + synergy card + guardrail badges |
| 8 | **Business value + ask** | Enterprise-ready (grounded, audited, public-web-scoped). Future: more depts, real-time alerts. Repo + demo links |

---

## 4. Final pre-submit checklist

- [ ] `.env` filled (BD key + zones, Gemini key, spend cap)
- [ ] `python run.py "Real Company" url:pricing url:jobs` ran ≥ 2 real accounts; `frontend/brief.json` refreshed
- [ ] `./demo.sh` boots, 54/54 tests pass, dashboard renders at :8000 (cytoscape graph visible, ▶ replay button animates, click-dept filters, dropped drawer expands)
- [ ] Deploy: drag `frontend/` to Vercel → public HTTPS URL captured
- [ ] Repo pushed public to `github.com/leonardtudor11/taki`
- [ ] Video recorded (≤ 5 min MP4) → unlisted YouTube
- [ ] Slides exported to PDF (8 slides)
- [ ] Cover image rendered (16:9)
- [ ] lablab form: paste fields above, attach cover/slides/video/repo/demo URLs
- [ ] Submit ✅

## 5. Demo record fail-safes

If a live re-record is needed during the deadline crunch:
- `./demo.sh` is idempotent — re-running just reopens the dashboard.
- The dashboard works offline once `frontend/brief.json` is checked in
  (it is, with the real Vercel cascade).
- If you accidentally overwrite `brief.json`, `git checkout frontend/brief.json` restores the cached Vercel run.
- The replay button drives the entire cascade animation from `brief.json` alone — no backend run needed during recording.
