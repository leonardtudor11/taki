"""Taki live entrypoint.

Tomorrow, with keys in .env:

    .venv/bin/python run.py "Stripe" \
        https://stripe.com/pricing:pricing \
        https://stripe.com/jobs:jobs

Scrapes once via Bright Data, runs the guarded cascade, caches the bundle +
brief, and refreshes frontend/brief.json so the dashboard shows it.

`generate_and_cache` is the offline-testable seam (inject fake LLMs); `run_live`
adds the Bright Data + Gemini wiring that needs credentials.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

from agents import orchestrator
from agents.schemas import CascadeBrief, SharedBundle, SourceType
from services import cache

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
FRONTEND_BRIEF = FRONTEND_DIR / "brief.json"
FRONTEND_EVENTS = FRONTEND_DIR / "events.jsonl"


def generate_and_cache(
    bundle: SharedBundle,
    gtm_llm=None,
    finance_llm=None,
    security_llm=None,
    strategy_llm=None,
    frontend_path: Path | None = FRONTEND_BRIEF,
    events_path: Path | None = None,
) -> CascadeBrief:
    """Persist bundle, run the LangGraph cascade, save brief, and (optionally)
    stream node events to a JSONL file the dashboard's replay mode can play back.
    """
    cache.save_bundle(bundle)
    # default the per-target events file alongside bundle.json / brief.json so
    # every run leaves an inspectable cascade trace next to its artifacts.
    target_events = cache.bundle_path(bundle.target).with_name("events.jsonl")
    brief = orchestrator.build_cascade_brief(
        bundle,
        gtm_llm=gtm_llm,
        finance_llm=finance_llm,
        security_llm=security_llm,
        strategy_llm=strategy_llm,
        event_path=target_events,
    )
    cache.save_brief(brief)
    if frontend_path is not None:
        frontend_path.write_text(brief.model_dump_json(indent=2))
        # mirror the trace beside the brief (same directory) so the static
        # dashboard can fetch it from the same origin without CORS friction.
        # Default = frontend/events.jsonl; tests passing a tmp brief get a
        # tmp events file in the same tmp dir (no repo pollution).
        events_target = events_path or (frontend_path.parent / "events.jsonl")
        if target_events.exists():
            events_target.write_text(target_events.read_text())
    return brief


def run_live(
    target: str,
    urls: list[tuple[str, SourceType]],
    reuse_cache: bool = True,
) -> CascadeBrief:
    """Live pipeline. If a cached bundle exists for the target and reuse_cache
    is True (default), skip the Bright Data pulls — only the LLM + cascade run.
    """
    bundle = cache.load_bundle(target) if reuse_cache else None
    if bundle is None:
        # imported lazily so offline tests never touch the network layer
        from services.brightdata import BrightDataClient, build_bundle

        client = BrightDataClient()
        bundle = build_bundle(target, client, urls)
    else:
        print(f"reusing cached bundle for {target} ({len(bundle.sources)} sources)")
    return generate_and_cache(bundle)


def _parse_urls(args: list[str]) -> list[tuple[str, SourceType]]:
    valid = {t.value for t in SourceType}
    out: list[tuple[str, SourceType]] = []
    for a in args:
        url, sep, kind = a.rpartition(":")
        # only treat the suffix as a source type if it actually is one,
        # otherwise the ':' belongs to the URL scheme (https://...)
        if sep and kind in valid:
            out.append((url, SourceType(kind)))
        else:
            out.append((a, SourceType.SITE))
    return out


def run_demo() -> CascadeBrief:
    """Generate a CascadeBrief from offline fixtures — no API keys required.

    Uses the Northwind Analytics fixture bundle and the canned fake-LLM
    responses. The fake GTM LLM intentionally tries to hallucinate a Globex
    acquisition; the grounding guard catches it, so the dashboard's dropped
    drawer renders with one real entry — proof the mechanism works without
    needing a live LLM run.
    """
    # imported lazily so a live run never imports test fixtures
    from fixtures.fake_llm import (
        fake_finance_llm,
        fake_gtm_llm_with_hallucination,
        fake_security_llm,
        fake_strategy_llm,
    )
    from fixtures.sample import sample_bundle

    return generate_and_cache(
        sample_bundle(),
        gtm_llm=fake_gtm_llm_with_hallucination,
        finance_llm=fake_finance_llm,
        security_llm=fake_security_llm,
        strategy_llm=fake_strategy_llm,
    )


def main() -> None:
    load_dotenv()
    if "--demo" in sys.argv:
        brief = run_demo()
        print(f"✓ demo brief generated · target: {brief.target}")
        print(f"  exec: {brief.executive_summary}")
        print(f"  dropped by grounding guard: "
              f"{len(brief.guardrail_report.ungrounded_dropped)}")
        print("  dashboard:  cd frontend && python3 -m http.server 8000")
        return
    if len(sys.argv) < 2:
        print('usage: python run.py [--demo | "Target" url:source_type ...]')
        raise SystemExit(2)
    target = sys.argv[1]
    urls = _parse_urls(sys.argv[2:])
    brief = run_live(target, urls)
    print(f"cached brief for {target}: {brief.executive_summary}")


if __name__ == "__main__":
    main()
