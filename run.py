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
    marketing_llm=None,
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
        marketing_llm=marketing_llm,
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
    industry: str = "",
    region: str = "",
    stage: str = "",
) -> CascadeBrief:
    """Live pipeline. If a cached bundle exists for the target and reuse_cache
    is True (default), skip the Bright Data pulls — only the LLM + cascade run.

    V7.41 — CLI now mirrors server.py target-mode for full coverage:
      • V7.22 SERP external-source discovery (reviews / HN / news /
        analyst URLs added to the bundle)
      • V7.33 academic + analyst SERP overlays
      • V7.36 LLM-generated industry-specific queries (when --industry
        passed)
      • V7.30 chrome fallback + V7.31 sub-page discovery (already in
        build_bundle since V7.30/31)
      • V7.38 competitor mini-bundle (post-cascade enrichment when
        profile_extract surfaces competitor_names)
    """
    client = None
    bundle = cache.load_bundle(target) if reuse_cache else None
    if bundle is None:
        # imported lazily so offline tests never touch the network layer
        from urllib.parse import urlparse as _urlparse

        from services.brightdata import (
            BrightDataClient, build_bundle,
            default_external_queries, discover_external_sources,
        )

        client = BrightDataClient()
        target_hosts = sorted({
            (_urlparse(u).hostname or "").lower()
            for u, _ in urls
            if _urlparse(u).hostname
        })

        # V7.22 + V7.33 base + academic + analyst SERP layers
        serp_queries = default_external_queries(target, industry=industry, region=region)

        # V7.36 — LLM-generated industry overlay (only when industry hint passed)
        if industry:
            try:
                from agents.query_generator import generate_queries_cached
                llm_queries = generate_queries_cached(
                    target=target, industry=industry,
                    region=region, stage=stage,
                )
                if llm_queries:
                    serp_queries = list(serp_queries) + llm_queries
                    print(f"+ {len(llm_queries)} LLM industry-specific SERP queries")
            except Exception as exc:
                print(f"(LLM query generator failed, falling back: {exc})")

        external = discover_external_sources(
            target=target, client=client, queries=serp_queries,
            exclude_hosts=target_hosts, n_per_query=3,
        )
        print(f"+ {len(external)} external sources discovered via SERP")

        bundle = build_bundle(
            target, client, urls + external,
            expand_url=(urls[0][0] if urls else None),
        )
        print(f"bundle built: {len(bundle.sources)} sources")
    else:
        print(f"reusing cached bundle for {target} ({len(bundle.sources)} sources)")
        # V7.38 still needs a client for post-cascade competitor enrichment.
        try:
            from services.brightdata import BrightDataClient
            client = BrightDataClient()
        except Exception:
            client = None

    brief = generate_and_cache(bundle)

    # V7.38 — post-cascade competitor mini-bundle (mirrors server.py).
    # profile_extract surfaces competitor_names during the cascade; we
    # enrich AFTER assemble so we have the names to work with.
    if (client is not None
            and brief.business_profile
            and brief.business_profile.competitor_names):
        try:
            from agents import competitor_summary
            print(f"+ enriching {min(len(brief.business_profile.competitor_names), competitor_summary.MAX_COMPETITORS)} competitors...")
            def _print_status(ev: dict) -> None:
                print(f"  competitor {ev.get('name')}: {ev.get('status')}")
            summaries = competitor_summary.build_summaries(
                target_name=brief.target,
                target_profile=brief.business_profile,
                competitor_names=brief.business_profile.competitor_names,
                client=client,
                on_event=_print_status,
            )
            if summaries:
                brief = brief.model_copy(update={"competitor_summaries": summaries})
                cache.save_brief(brief)
                if FRONTEND_BRIEF.parent.exists():
                    FRONTEND_BRIEF.write_text(brief.model_dump_json(indent=2))
                print(f"+ {len(summaries)} competitor summaries shipped")
        except Exception as exc:
            print(f"(competitor enrichment failed: {exc})")

    return brief


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
        fake_marketing_llm,
        fake_security_llm,
        fake_strategy_llm,
    )
    from fixtures.sample import sample_bundle

    return generate_and_cache(
        sample_bundle(),
        gtm_llm=fake_gtm_llm_with_hallucination,
        finance_llm=fake_finance_llm,
        marketing_llm=fake_marketing_llm,
        security_llm=fake_security_llm,
        strategy_llm=fake_strategy_llm,
    )


def _extract_flag(argv: list[str], name: str) -> str:
    """Pull --name=value or --name value from argv (mutates argv). Returns ''
    when flag absent. Supports both --industry=Saas and --industry SaaS forms."""
    for i, a in enumerate(argv):
        if a == f"--{name}" and i + 1 < len(argv):
            val = argv[i + 1]
            del argv[i:i + 2]
            return val.strip()
        if a.startswith(f"--{name}="):
            val = a.split("=", 1)[1]
            del argv[i]
            return val.strip()
    return ""


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
    argv = list(sys.argv[1:])
    # V7.41 — optional industry / region / stage / --no-cache flags
    industry = _extract_flag(argv, "industry")
    region   = _extract_flag(argv, "region")
    stage    = _extract_flag(argv, "stage")
    no_cache = "--no-cache" in argv
    if no_cache:
        argv.remove("--no-cache")
    if not argv:
        print('usage: python run.py [--demo | "Target" url:source_type ... '
              '[--industry "..."] [--region "..."] [--stage "..."] [--no-cache]]')
        raise SystemExit(2)
    target = argv[0]
    urls = _parse_urls(argv[1:])
    brief = run_live(target, urls, reuse_cache=(not no_cache),
                     industry=industry, region=region, stage=stage)
    print(f"cached brief for {target}: {brief.executive_summary}")


if __name__ == "__main__":
    main()
