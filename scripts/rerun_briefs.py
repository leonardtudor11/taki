"""V7.28 — rerun cached target-mode briefs with the new strategy prompt.

Reuses each target's cached SharedBundle (data/<slug>/bundle.json) so the
Bright Data scrape is skipped — only the LLM cascade re-runs. Writes the
output to frontend/briefs/<slug>.json (NOT frontend/brief.json) so the
Orchid default stays intact for the Vercel landing page.

Usage:  .venv/bin/python scripts/rerun_briefs.py
Cost:   ~$0.10-0.30 per target (Vertex Gemini calls only — BD skipped)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from agents import cascade_graph  # noqa: E402  imported after sys.path + load_dotenv
from agents.schemas import CascadeMode  # noqa: E402
from services import cache  # noqa: E402

BRIEFS_DIR = ROOT / "frontend" / "briefs"
BRIEFS_DIR.mkdir(exist_ok=True)

TARGETS = [
    ("Supabase", "supabase"),
    ("Notion",   "notion"),
    ("Pfizer",   "pfizer"),
]


def _profile_summary(brief) -> str:
    bp = brief.business_profile
    if not bp:
        return "industry=? stage=?"
    industry = (getattr(bp, "industry", None) or "?")[:40]
    stage = getattr(bp, "stage", None)
    stage_val = stage.value if hasattr(stage, "value") else str(stage or "?")
    return f"industry={industry!r} stage={stage_val}"


def _plays_summary(brief) -> str:
    if not brief.strategic_plan:
        return "plays=0 (no plan)"
    plays = brief.strategic_plan.recommended_plays or []
    with_cites = sum(1 for p in plays if p.citations)
    return f"plays={len(plays)} with_cites={with_cites}"


for i, (name, slug) in enumerate(TARGETS):
    if i > 0:
        print(f"\n…sleeping 90s (Vertex 429 guard)…")
        time.sleep(90)
    print(f"\n→ rerunning {name}")
    bundle = cache.load_bundle(name)
    if bundle is None:
        print(f"  ✗ no cached bundle for {name} — skip")
        continue
    print(f"  bundle: {len(bundle.sources)} sources")
    brief = cascade_graph.run(bundle, mode=CascadeMode.TARGET)
    cache.save_brief(brief)
    out = BRIEFS_DIR / f"{slug}.json"
    out.write_text(brief.model_dump_json(indent=2))
    print(f"  ✓ {out.name}  {_profile_summary(brief)}  {_plays_summary(brief)}")
    print(f"  exec: {brief.executive_summary[:160]}")

print("\ndone.")
