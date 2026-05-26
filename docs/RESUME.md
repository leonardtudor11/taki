# Resume Prompt — paste into a fresh Claude session in ~/taki

Copy everything inside the fence below into the first message of the new session.

---

```
You are resuming work on **Taki** — Bright Data "Web Data UNLOCKED" hackathon
project at ~/taki. lablab.ai submission, primary Track 1 GTM with Finance +
Security as feeder departments. Deadline: May 30 build / May 31 finale.

## Boundary (security)
- Only read/write/run inside /Users/mirel-leonardtudor/taki.
- No personal files, no other projects, no ~/.env, no credentials/SA files.
- Every session ends in a git commit. Rollback = git reset.

## Current state — LIVE end-to-end (verified May 26)
- Backend: 3 dept agents (GTM/Finance/Security), 3 guardrails (grounding/PII/leak),
  orchestrator builds CascadeBrief. 50 tests passing.
- Auth wired: Vertex AI via ADC at ~/.config/gcloud/adc_taki.json
  (project: project-2be42b84-14e0-421a-b3a). Bright Data via Unlocker zone
  "taci_unlocker". SERP/Scraper zones unused (Path A — make optional).
- Real run on Vercel succeeded: data/vercel/brief.json + frontend/brief.json
  (2 buying / 1 hiring signals; 2 pricing moves; 9 risk signals;
   8 ungrounded LLM claims caught by grounding guard, passed=False — guard working).
- Static HTML/JS dashboard at frontend/ — reads brief.json. View locally:
  `cd ~/taki/frontend && python3 -m http.server 8000` → http://localhost:8000.

## Read first
- docs/STATUS.md — per-session build log
- docs/HANDOFF.md — operational steps (auth, run, deploy)
- docs/PRESENTATION.md — full lablab form text + 5-min video script + 8-slide outline
- README.md — architecture diagram + run/test
- agents/, services/, guardrails/, frontend/, tests/ — the code

## Active /ultraplan upgrade — V1 → V3 → V4 → V2

User feedback: current dashboard "looks like crucible/diligence." Distinctive
identity + interactive cascade graph + real LangGraph backend agreed. Strictly
vanilla HTML/JS frontend — NO React, NO build step. All libs via CDN. Static
files deploy to Vercel free tier.

### V1 — Logo + identity reset (START HERE)
- Direction B chosen: geometric monoline 滝 stylized as **3 descending streams**
  (one per department: GTM cyan, Finance green, Security amber). SVG inline.
- Refresh palette + typography to clearly differ from diligence's dark-panel
  aesthetic. Consider a less stock-dev look — asymmetric layout, less-grid feel.
- Touch frontend/index.html only. Keep app.js + cascade-flow.js rendering logic.

### V3 — Interactive cascade graph (cytoscape.js)
- Replace static cascade-flow strip with a real node-edge graph:
  3 dept nodes + handoff edges with labels + synergy connectors.
- Add cytoscape via CDN. GSAP for entry animation (also CDN).
- Click a dept node → fades the other panels, highlights that dept's claims.

### V4 — UI/UX polish
- Invoke ui-ux-pro-max skill for spacing/typography/motion guidance.
- Reference 21st.dev component patterns; extract as vanilla HTML/JS, NOT React.

### V2 — Real LangGraph backend
- Rewrite agents/orchestrator.py to use langgraph.StateGraph: parallel dept
  nodes (async + reducer), guardrail node, synthesis node. Same CascadeBrief
  output — frontend untouched.
- Optionally stream intermediate state to data/<slug>/cascade-trace.json.

## After the V-phases
- S4.4 Deploy frontend/ to Vercel (drag-drop or vercel CLI). Public HTTPS URL.
- S5.2 Record 5-min MP4 demo (script in docs/PRESENTATION.md).
- S5.3 Push public repo (github.com/leonardtudor11/taki); submit lablab form.

## Useful commands
- Tests: `.venv/bin/python -m pytest -q`
- Live run: `.venv/bin/python run.py "Company" https://x/pricing:pricing https://x/jobs:jobs`
  (reuses cached bundle if present — only LLM cost on re-run)
- Dashboard: `cd frontend && python3 -m http.server 8000`
- Auth check: `gcloud auth application-default print-access-token` (with
  `GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/adc_taki.json` for Taki's ADC)

## Discipline
- Ultraplan style: ONE step at a time, build → test → commit per session.
- Karpathy principles always on (from ~/.claude/CLAUDE.md): simplicity first,
  surgical changes, goal-driven, think-before-coding.
- Caveman compression on by default. Drop articles, fluff, hedging.

Start at V1 Step 1: design and inline the SVG monoline 滝 logo (3-stream cascade)
+ the refreshed palette/typography in frontend/index.html. Show me a preview
description (or open the local server) before committing.
```

---

## How to use

1. Stop the current Claude session (or wait for it to compact).
2. Start a fresh Claude Code session, cd to ~/taki.
3. Paste the block above as your first message.
4. The new session has the full plan + state and starts at V1.
