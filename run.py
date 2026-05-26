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

FRONTEND_BRIEF = Path(__file__).resolve().parent / "frontend" / "brief.json"


def generate_and_cache(
    bundle: SharedBundle,
    gtm_llm=None,
    finance_llm=None,
    security_llm=None,
    frontend_path: Path | None = FRONTEND_BRIEF,
) -> CascadeBrief:
    cache.save_bundle(bundle)
    brief = orchestrator.build_cascade_brief(
        bundle, gtm_llm=gtm_llm, finance_llm=finance_llm, security_llm=security_llm
    )
    cache.save_brief(brief)
    if frontend_path is not None:
        frontend_path.write_text(brief.model_dump_json(indent=2))
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


def main() -> None:
    load_dotenv()
    if len(sys.argv) < 2:
        print('usage: python run.py "Target" [url:source_type ...]')
        raise SystemExit(2)
    target = sys.argv[1]
    urls = _parse_urls(sys.argv[2:])
    brief = run_live(target, urls)
    print(f"cached brief for {target}: {brief.executive_summary}")


if __name__ == "__main__":
    main()
