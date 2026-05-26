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

## Stop protocol (unattended runs)
At each session: build → test → (audit) → update this table → `git commit`. If a session is BLOCKED (missing key/auth/decision): mark it, skip to the next *independent* session that is fixture-testable, and log the blocker here. Never fake a passing test.

---

## Live state (May 26)
- Vertex AI: live via ADC at `~/.config/gcloud/adc_taki.json` (project `project-2be42b84-14e0-421a-b3a`).
- Bright Data: live via Unlocker zone `taci_unlocker` (~$0.0015/req).
- Real run: `data/vercel/brief.json` (2 buying / 1 hiring / 2 pricing / 9 risk; 8 ungrounded dropped → guardrail working).
- Tests: 50/50.

## Active /ultraplan upgrade — V1→V3→V2→V3.2→V4→demo

All V-phases complete. 54/54 tests pass.

- **V1.1** Logo + identity reset — ✅ inline SVG monoline 滝 (3 cyan/green/amber streams w/ draw-in), warm-ink palette, Fraunces+Inter+JBMono mix, vermilion 朱 accent, left stream-lane gutter, panel-less columns.
- **V3** Interactive cytoscape graph — ✅ 5-node graph (Bright Data · GTM · Finance · Security · CascadeBrief), feed/output/handoff/synergy edges, cascade entry animation, click-dept focus filter, hover-edge tooltip, text fallback if CDN unreachable.
- **V2** Real LangGraph backend — ✅ `agents/cascade_graph.py` StateGraph with explicit parallel dept fan-out + grounding join + cross-pollination + assemble nodes. Each node emits JSON events to `data/<slug>/events.jsonl` + `frontend/events.jsonl`. `build_cascade_brief` delegates here.
- **V3.2** Replay-cascade mode — ✅ "▶ replay cascade" button on the dashboard animates the entire pipeline from brief.json (PII → leak → 3 depts → grounding → handoffs → synergies → assemble) with timed cytoscape pulses + tooltip narration. No backend trace needed at deploy time.
- **V4** UX polish — ✅ dept-coloured confidence bars on every claim; expandable "Hallucinations caught" drawer listing every dropped claim verbatim; ARIA regions; :focus-visible vermilion rings; mobile breakpoints (≤960 / ≤600); prefers-reduced-motion respected.
- **Demo** — ✅ `./demo.sh` one-command boot (venv, deps, tests, server, browser); `run.py --demo` regenerates brief from offline fixtures (with planted Globex hallucination → grounding guard catches); README rewritten with 60-second-demo block at the top + Stack table; PRESENTATION.md video script rewritten around the new dashboard actions (replay button, click-filter, dropped drawer).

See `docs/RESUME.md` for the full resume prompt to paste into a fresh session.
