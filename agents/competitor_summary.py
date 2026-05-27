"""V7.38 — Competitor mini-bundle (lightweight gap #3).

For each NAMED competitor in business_profile.competitor_names (capped
at 3), produce a CompetitorSummary:
  1. SERP for the competitor's primary URL ("{name}" official site)
  2. Unlock that URL → homepage HTML → text (with the V7.30 JS-chrome
     fallback wired in so a JS-blocked competitor SPA still gets
     Wikipedia / Wayback content for the LLM)
  3. ONE LLM call extracting positioning + pricing + stage + a
     1-sentence "why_relevant" tying back to the TARGET's industry
     and stage so the summary isn't generic boilerplate

Runs post-cascade (in server.py / run.py), AFTER profile_extract has
populated competitor_names — that's why this isn't a cascade graph
node: profile_extract runs mid-cascade so its output isn't available
until assemble fires.

Cost cap: 3 competitors × (1 SERP + 1 Unlock + 1 LLM) ≈ $0.10-$0.15
per cascade. Soft-fail per competitor — a missing primary URL or a
chrome-blocked homepage drops THAT entry, never the whole list.
"""

from __future__ import annotations

import json
import urllib.parse

from agents.base import strip_fences
from agents.schemas import BusinessProfile, CompetitorSummary
from services.brightdata import (
    BrightDataClient,
    _clean_serp_url,
    fetch_js_chrome_fallbacks,
    html_to_text,
    looks_like_js_chrome,
    parse_serp_results,
)
from services.llm import LLMFn, get_default_llm
from services.url_audit import is_low_quality

DEPT = "competitor_summary"
MAX_COMPETITORS = 3

_PROMPT = """You are reading a competitor's homepage to build a 4-field
mini-summary for a strategic brief about the TARGET company "{target}"
(industry: {target_industry}, stage: {target_stage}).

COMPETITOR NAME: {name}
COMPETITOR PRIMARY URL: {url}
COMPETITOR HOMEPAGE TEXT:
{text}

Return JSON ONLY (no prose, no markdown fences):
{{
  "positioning":  "1 sentence: what they sell and to whom. Specific phrasing from THEIR copy — not generic.",
  "pricing_hint": "1 fragment: pricing observed or implied. e.g. '$99/seat/mo and up' OR 'enterprise sales-led, no public pricing' OR 'free + paid tier ($12/mo)'. Use 'unstated' if invisible.",
  "stage_hint":   "1 word: idea | mvp | pre-revenue | early-revenue | growth | scale",
  "why_relevant": "1 sentence tying this competitor to {target}: where they directly compete OR where they take a different bet. Reference specific {target}-context (industry/stage)."
}}

Rules:
  - All four fields REQUIRED — return shortened versions if a field is
    inferred rather than directly stated.
  - 'why_relevant' MUST mention {target} or its industry. Generic
    descriptions of the competitor are not enough.
  - Empty / illegible homepage → skip the entry by returning {{}}.
Output JSON only."""


def _serp_primary_url(client: BrightDataClient, name: str) -> str | None:
    """Use SERP to find a competitor's primary URL.

    Strategy: search for the name + 'official site', take the first
    non-google result whose hostname plausibly looks like the
    competitor's brand. Falls back to the first non-google result.
    Returns None if SERP returns nothing usable.
    """
    if not client.serp_zone and not client.unlocker_zone:
        return None
    try:
        # Prefer SERP zone when configured, else hit google via Unlocker.
        if client.serp_zone:
            html = client.serp(f'{name} official site')
        else:
            q = urllib.parse.quote(f'{name} official site')
            html = client.unlock(f"https://www.google.com/search?q={q}")
    except Exception:
        return None
    urls = parse_serp_results(html, exclude_hosts=set(), max_urls=10)
    if not urls:
        return None
    # Heuristic: pick first URL whose host token contains a normalized
    # version of the name (lowercased, no spaces).
    name_token = "".join(ch for ch in name.lower() if ch.isalnum())
    for u in urls:
        host = (urllib.parse.urlparse(u).hostname or "").lower()
        if name_token and name_token in host.replace(".", "").replace("-", ""):
            return _clean_serp_url(u)
    # Fallback: first result.
    return _clean_serp_url(urls[0])


def _scrape_with_fallback(
    client: BrightDataClient,
    url: str,
    name: str,
    cap_chars: int = 8000,
) -> str:
    """Unlock URL + return body text. If the response looks like JS
    chrome, use V7.30 fetch_js_chrome_fallbacks to pull
    en.wikipedia.org/{name} + Wayback snapshot, and concatenate their
    bodies as supplementary text. Returns empty string on total failure.
    """
    try:
        text = html_to_text(client.unlock(url))[:cap_chars]
    except Exception:
        text = ""
    if not text:
        return ""
    bad, _ = is_low_quality(text)
    if bad:
        return ""
    is_chrome, _ = looks_like_js_chrome(text)
    if is_chrome:
        # Reuse V7.30 fallback chain — wikipedia of competitor name + wayback.
        fallbacks = fetch_js_chrome_fallbacks(
            target=name, chrome_url=url, client=client, cap_chars=cap_chars,
        )
        if fallbacks:
            # Concatenate fallback bodies onto the (thin) chrome body.
            text = text + "\n\n" + "\n\n".join(
                (it.text or "")[:cap_chars] for it in fallbacks
            )
    return text


def _llm_extract(
    name: str,
    url: str,
    text: str,
    target: str,
    target_profile: BusinessProfile | None,
    llm: LLMFn,
) -> CompetitorSummary | None:
    target_industry = (target_profile.industry if target_profile else "") or "(unknown)"
    target_stage    = (target_profile.stage    if target_profile else "") or "(unknown)"
    # Trim text so prompt stays under ~12k tokens; competitor homepage
    # usually has the positioning in the first ~4k chars anyway.
    prompt = _PROMPT.format(
        target=target,
        target_industry=target_industry,
        target_stage=target_stage,
        name=name,
        url=url,
        text=text[:4500],
    )
    try:
        raw = llm(prompt)
        obj = json.loads(strip_fences(raw))
    except Exception:
        return None
    if not isinstance(obj, dict) or not obj:
        return None
    # All four fields required; empty/missing → drop.
    fields = ("positioning", "pricing_hint", "stage_hint", "why_relevant")
    if not all((obj.get(f) or "").strip() for f in fields):
        return None
    return CompetitorSummary(
        name=name,
        url=url,
        positioning=str(obj["positioning"])[:240],
        pricing_hint=str(obj["pricing_hint"])[:120],
        stage_hint=str(obj["stage_hint"])[:40],
        why_relevant=str(obj["why_relevant"])[:240],
        citation=url,
    )


def build_summaries(
    target_name: str,
    target_profile: BusinessProfile | None,
    competitor_names: list[str],
    client: BrightDataClient,
    llm: LLMFn | None = None,
    max_competitors: int = MAX_COMPETITORS,
    on_event=None,
) -> list[CompetitorSummary]:
    """Build per-competitor mini-summaries. Caps at max_competitors.

    `on_event` (optional) emits dicts per competitor with status:
    'lookup_failed' / 'scrape_failed' / 'llm_failed' / 'ok' — so
    server can stream progress via SSE.

    Never raises — per-competitor failures degrade silently to a
    skipped entry. Returns possibly-empty list.
    """
    if not competitor_names:
        return []
    llm = llm or get_default_llm()

    out: list[CompetitorSummary] = []
    seen_urls: set[str] = set()

    def _emit(name: str, status: str, **kw) -> None:
        if on_event is None:
            return
        try:
            on_event({"name": name, "status": status, **kw})
        except Exception:
            pass

    for raw_name in competitor_names[:max_competitors]:
        name = (raw_name or "").strip()
        if not name:
            continue
        url = _serp_primary_url(client, name)
        if not url or url in seen_urls:
            _emit(name, "lookup_failed", reason="no SERP hit" if not url else "duplicate")
            continue
        seen_urls.add(url)
        text = _scrape_with_fallback(client, url, name)
        if not text:
            _emit(name, "scrape_failed", url=url)
            continue
        summary = _llm_extract(name, url, text, target_name, target_profile, llm)
        if not summary:
            _emit(name, "llm_failed", url=url)
            continue
        out.append(summary)
        _emit(name, "ok", url=url)
    return out
