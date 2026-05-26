# Taki — Build Status

Checkpoint log. One row per session. Updated at the end of each session before commit.

| Session | What | State | Tested | Audited | Commit | Notes / blockers |
|---|---|---|---|---|---|---|
| S0.1 | Repo scaffold | ✅ done | n/a | n/a | (initial) | dirs + venv + git + env template |
| S0.2 | Bright Data client + live smoke | ✅ done | 4/4 + live | self | (S0.2) | live smoke on example.com returned 528B, spent $0.001 |
| S0.3 | Shared cache + Pydantic schemas | ✅ done | 8/8 | self | (S0.3) | data contract + fixture w/ planted PII+confidential |
| S1.1 | GTM agent → AccountBrief | ✅ done | 2/2 | self | (S1.1) | + agent base + injectable LLM + fake_llm fixtures |
| S1.2 | Finance agent → MarketSignal | ✅ done | 2/2 | self | (S1.2) | grounded, injectable LLM |
| S1.3 | Security agent → RiskProfile | ✅ done | 2/2 | self | (S1.3) | grounded, injectable LLM |
| S2.1 | Grounding/citation guard | ✅ done | 3/3 | self | (S2.1) | drops hallucinated + uncited claims |
| S2.2 | PII redaction | ✅ done | 3/3 | self | (S2.2) | emails+phones redacted; prices/counts preserved |
| S2.3 | Leak/scope guard | ✅ done | full 17/17 | self | (S2.3) | withholds confidential-marked sources |
| S3.1 | Orchestrator skeleton | ✅ done | 1/1 | self | (S3.1) | runs 3 depts on shared bundle |
| S3.2 | Cross-pollination + handoffs | ✅ done | 3/3 | self | (S3.2) | synergy needs ≥2 depts; 3 handoffs |
| S3.3 | Wire guardrails + Cascade Brief | ✅ done | full 30/30 | self | (S3.3) | PII→leak→depts→grounding→synergy→brief; hallucination caught |
| S4.1 | Dashboard shell + dept panels | ✅ done | contract 3/3 | self | (S4.1) | static HTML/JS (no npm); ⚠️ browser visual check pending |
| S4.2 | Cascade-flow + handoff visual | ✅ done | contract 4/4 | self | (S4.2) | dept nodes + handoff wires; ⚠️ browser visual pending |
| S4.3 | Pull Fresh live button | 🟡 pipeline done | 2/2 | self | (S4.3) | run.py live entrypoint built+tested offline; UI button = stub; **LIVE BLOCKED on keys** |
| S4.4 | Deploy Vercel + cache accounts | ⏳ pending | — | — | — | **NEEDS YOU: Vercel auth** |
| S5.1 | README + arch diagram + LICENSE | ✅ done | n/a | self | (S5.1) | + real example brief.json artifact |
| S5.2 | Video + slides | 🟡 text drafted | n/a | self | (audit pass) | full 5-min script + 8-slide outline in docs/PRESENTATION.md — record/export pending |
| S5.3 | Public repo + lablab form | 🟡 text drafted | n/a | self | (audit pass) | every form field + BD usage statement drafted — push + submit pending |
| S6.1 | V-phase upgrade (V1+V3+V2+V3.2+V4+demo) | ✅ done | 54/54 | self | (V1.1/V3/V2/V3.2/V4/demo) | logo+identity · cytoscape graph · LangGraph backend · replay mode · UX polish · `./demo.sh` end-to-end demo + `run.py --demo` fixture path |
| S6.2 | V5 live mode + label-clarity fix | ✅ done | 59/59 | self | (label-fix + live-mode) | Flask SSE backend (`server.py`) drives cytoscape in real time · 3 toolbar buttons (replay / live demo / live run popover) · per-edge arc classes + opaque-bg labels = no clipping/overlap · 5 new server tests |
| S6.3 | V6 Strategy department + plan hero | ✅ done | 64/64 | self | (V6) | 4th agent (Chief of Staff) synthesizes a real StrategicPlan: headline · narrative · ICP fit · deal-size · urgency · 3-5 prioritized plays (priority + timeframe + dept owners + citations) · open questions. New StateGraph node `strategy` between cross_pollinate and assemble. Hero section above the cascade graph. Replay + SSE animate the strategy phase. Strategy failure contained (brief still assembled). Richer fixtures (3 → 13 grounded claims) + Vercel cached plan hand-crafted. |

## Stop protocol (unattended runs)
At each session: build → test → (audit) → update this table → `git commit`. If a session is BLOCKED (missing key/auth/decision): mark it, skip to the next *independent* session that is fixture-testable, and log the blocker here. Never fake a passing test.

---

## Live state (May 26)
- Vertex AI: live via ADC at `~/.config/gcloud/adc_taki.json` (project `project-2be42b84-14e0-421a-b3a`).
- Bright Data: live via Unlocker zone `taci_unlocker` (~$0.0015/req).
- Real run: `data/vercel/brief.json` (2 buying / 1 hiring / 2 pricing / 9 risk; 8 ungrounded dropped → guardrail working).
- Tests: 50/50.

## Active /ultraplan upgrade — V1→V3→V2→V3.2→V4→demo→live→V6

All V-phases complete. 64/64 tests pass.

- **V1.1** Logo + identity reset — ✅ inline SVG monoline 滝 (3 cyan/green/amber streams w/ draw-in), warm-ink palette, Fraunces+Inter+JBMono mix, vermilion 朱 accent, left stream-lane gutter, panel-less columns.
- **V3** Interactive cytoscape graph — ✅ 5-node graph (Bright Data · GTM · Finance · Security · CascadeBrief), feed/output/handoff/synergy edges, cascade entry animation, click-dept focus filter, hover-edge tooltip, text fallback if CDN unreachable.
- **V2** Real LangGraph backend — ✅ `agents/cascade_graph.py` StateGraph with explicit parallel dept fan-out + grounding join + cross-pollination + assemble nodes. Each node emits JSON events to `data/<slug>/events.jsonl` + `frontend/events.jsonl`. `build_cascade_brief` delegates here.
- **V3.2** Replay-cascade mode — ✅ "▶ replay cascade" button on the dashboard animates the entire pipeline from brief.json (PII → leak → 3 depts → grounding → handoffs → synergies → assemble) with timed cytoscape pulses + tooltip narration. No backend trace needed at deploy time.
- **V4** UX polish — ✅ dept-coloured confidence bars on every claim; expandable "Hallucinations caught" drawer listing every dropped claim verbatim; ARIA regions; :focus-visible vermilion rings; mobile breakpoints (≤960 / ≤600); prefers-reduced-motion respected.
- **Demo** — ✅ `./demo.sh` one-command boot (venv, deps, tests, server, browser); `run.py --demo` regenerates brief from offline fixtures (with planted Globex hallucination → grounding guard catches).
- **V5 live mode** — ✅ `server.py` (Flask + flask-cors) serves the static dashboard at :5001 AND a POST /api/run SSE endpoint streaming every cascade event. Two real backend modes: `demo` (fixture + fake LLMs, no keys) and `live` (Bright Data + Vertex/Gemini, .env required). Cytoscape animates in real time from each SSE event — not scripted. `./demo.sh` now boots `server.py`. 5 new tests in `tests/test_server.py`. Edge labels: short keyword topics (no '…' clipping), per-edge arc classes so handoff labels don't stack, opaque-bg + text-outline for readability over any overlap.
- **V6 Strategy department** — ✅ 4th agent — Chief of Staff — sits between cross_pollinate and assemble. Reads all 3 dept outputs + synergies + handoffs and produces a `StrategicPlan` (Pydantic): headline · 3-paragraph narrative · ICP fit (high/medium/low) · deal-size range · urgency · 3-5 prioritized plays (priority 1-5, timeframe, dept owners, rationale, citations) · open questions. Failure-isolated: a broken strategy LLM doesn't lose the rest of the cascade. New `agents/strategy.py` + LangGraph node + 5 strategy tests. Dashboard renders the plan as a hero section above the cascade graph (big Fraunces headline, narrative paragraphs, 3-col stat grid, priority-colored numbered plays, open-questions drawer). Replay + SSE handle the strategy phase. Sample fixtures enriched 3 → ~13 grounded claims so the offline demo doesn't read thin. Vercel cached brief hand-patched with a representative StrategicPlan (5 plays, 5 open questions, high ICP fit, $80-240k ARR estimate, act-this-half urgency).

See `docs/RESUME.md` for the full resume prompt to paste into a fresh session.
