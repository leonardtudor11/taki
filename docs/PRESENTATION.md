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

### Scene 1 — Hook (0:00–0:30)
> "Most 'AI for revenue' is one LLM staring at one feed. Real companies don't work that way. Sales, Finance, and GRC each look at the same account through different lenses — and they talk to each other. **Taki** — Japanese for cascade — models that."
>
> [Visual: open the dashboard at the cached "Northwind Analytics" brief.]

### Scene 2 — The cascade in action (0:30–1:30)
> "One target. Three department agents share ONE live web data bundle — pulled via Bright Data, scraped once, consumed by everyone. That's the Lean principle."
>
> [Visual: scroll to the three dept panels. Read one claim from each, click the citation chip — it links to the live source URL.]
>
> "GTM sees the buying signals. Finance sees the pricing move. Security sees the reputational drag from that pricing move. And then" — [scroll to cascade-flow strip] — "they hand off to each other: Finance tells GTM 'pricing changed — adjust outreach.' Security tells GTM 'reputational signal — frame responsibly.' GTM tells Security 'hiring expansion — new attack surface.' Real cross-department communication."

### Scene 3 — Synergy + guardrails (1:30–3:00)
> "And then the synergy pass." [scroll to synergy card] "Pricing increase + support complaints — neither department alone would say 'churn risk.' Together they do. That's the cross-functional signal you can't get from one agent."
>
> [Scroll to guardrail badges.]
>
> "And Compliance audits everyone. The Security department isn't just a producer — it's the guardrail layer. Three guardrails: PII gets redacted before any LLM call. Confidential-marked sources get withheld entirely. And every claim must cite a snippet that actually exists in the scraped bundle — if the LLM hallucinates a fact, the grounding guard drops it and logs it. Look at the badges: two PII redactions caught, one source withheld."
>
> [Quick demo: open `data/northwind-analytics/brief.json`, point to `guardrail_report.ungrounded_dropped`.]

### Scene 4 — Bright Data is the magic (3:00–4:00)
> "None of this works without Bright Data. The whole point: live, bot-bypassable, public web data, fresh — not last week's export. SERP zone discovers the sources, Web Unlocker pulls the pages past bot-blocking. One shared cache, every department reads it."
>
> [Show `services/brightdata.py` briefly. Spend cap line highlighted.]
>
> "And we built a spend cap so an unattended run can never burn the credit."

### Scene 5 — Enterprise fit + close (4:00–5:00)
> "Why does this matter? Because a single-LLM brief is unsafe for enterprise. PII leaks, confidential bleed-through, hallucinations cost trust. Taki is built so a real GRC team would let it into production: every claim grounded, every output audited, every source scoped to public web."
>
> "Same architecture metaphor as how a company actually works — departments, cross-talk, compliance auditing everyone. One shared data layer, Bright Data. One unified deliverable. Taki."
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
- [ ] `python -m http.server` in `frontend/`, dashboard rendered visually (no JS errors, panels populated, handoff wires visible)
- [ ] Deploy: drag `frontend/` to Vercel → public HTTPS URL captured
- [ ] Repo pushed public to `github.com/leonardtudor11/taki`
- [ ] Video recorded (≤ 5 min MP4) → unlisted YouTube
- [ ] Slides exported to PDF (8 slides)
- [ ] Cover image rendered (16:9)
- [ ] lablab form: paste fields above, attach cover/slides/video/repo/demo URLs
- [ ] Submit ✅
