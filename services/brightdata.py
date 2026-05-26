"""Bright Data client — the live web data layer.

Wraps the Bright Data unified request API (SERP, Web Unlocker, Scraper zones).
Reads credentials from .env. A SpendTracker enforces TAKI_BD_SPEND_CAP so an
unattended run can never burn the whole credit.

Wired but live calls need BRIGHTDATA_API_KEY + zones. Pure helpers (payload,
spend tracking, html->text) are unit-tested offline; the live smoke test is
gated on keys.
"""

from __future__ import annotations

import os
import re
import urllib.parse

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from agents.schemas import SharedBundle, SourceItem, SourceSubject, SourceType
from services.url_audit import is_low_quality

_API = "https://api.brightdata.com/request"


class BudgetExceeded(RuntimeError):
    pass


class SpendTracker:
    """Soft spend guard. Estimates cost per request and refuses to exceed the cap."""

    def __init__(self, cap_usd: float, cost_per_request: float = 0.001):
        self.cap_usd = cap_usd
        self.cost_per_request = cost_per_request
        self.spent = 0.0

    def charge(self) -> None:
        if self.spent + self.cost_per_request > self.cap_usd:
            raise BudgetExceeded(
                f"Bright Data spend cap ${self.cap_usd} would be exceeded "
                f"(spent ${self.spent:.3f})."
            )
        self.spent += self.cost_per_request


def build_payload(zone: str, url: str, fmt: str = "raw") -> dict:
    return {"zone": zone, "url": url, "format": fmt}


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class BrightDataClient:
    def __init__(
        self,
        api_key: str | None = None,
        serp_zone: str | None = None,
        unlocker_zone: str | None = None,
        scraper_zone: str | None = None,
        tracker: SpendTracker | None = None,
    ):
        self.api_key = api_key or os.environ.get("BRIGHTDATA_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "BRIGHTDATA_API_KEY not set — add it (and zones) to .env for live runs."
            )
        self.serp_zone = serp_zone or os.environ.get("BRIGHTDATA_SERP_ZONE", "")
        self.unlocker_zone = unlocker_zone or os.environ.get(
            "BRIGHTDATA_UNLOCKER_ZONE", ""
        )
        self.scraper_zone = scraper_zone or os.environ.get("BRIGHTDATA_SCRAPER_ZONE", "")
        self.tracker = tracker or SpendTracker(
            float(os.environ.get("TAKI_BD_SPEND_CAP", "50"))
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def _request(self, zone: str, url: str, fmt: str = "raw") -> str:
        # 30s per attempt (was 90s) — with 3 retries the worst-case is ~90s
        # per URL instead of 270s. Self-mode often runs 4+ URLs, so cutting
        # the per-URL ceiling makes a 'one bad URL' run finish in minutes
        # rather than freezing the entire cascade.
        self.tracker.charge()
        resp = httpx.post(
            _API,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=build_payload(zone, url, fmt),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.text

    def serp(self, query: str) -> str:
        q = urllib.parse.quote(query)
        return self._request(self.serp_zone, f"https://www.google.com/search?q={q}")

    def unlock(self, url: str) -> str:
        return self._request(self.unlocker_zone, url)


def build_bundle(
    target: str,
    client: BrightDataClient,
    urls: list[tuple[str, SourceType]] | None = None,
    cap_chars: int = 8000,
) -> SharedBundle:
    """Scrape once into a SharedBundle.

    Optional SERP discovery pass (only if a SERP zone is configured), then each
    explicitly-provided URL via Unlocker. Path A demos run with URLs only.
    """
    sources: list[SourceItem] = []
    if client.serp_zone:
        sources.append(
            SourceItem(
                source_type=SourceType.SERP,
                url=f"serp:{target}",
                text=html_to_text(
                    client.serp(f"{target} pricing careers news")
                )[:cap_chars],
            )
        )
    for url, stype in urls or []:
        sources.append(
            SourceItem(
                source_type=stype,
                url=url,
                text=html_to_text(client.unlock(url))[:cap_chars],
            )
        )
    return SharedBundle(target=target, sources=sources)


def _hostname(url: str) -> str:
    try:
        h = urllib.parse.urlparse(url).hostname or url
        # strip leading www. so brands read clean
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return url


def build_self_bundle(
    business_name: str,
    self_urls: list[tuple[str, SourceType]],
    competitor_urls: list[tuple[str, SourceType]],
    client: BrightDataClient,
    cap_chars: int = 8000,
    on_error=None,
) -> tuple[SharedBundle, list[dict]]:
    """Scrape the founder's own URLs (subject=self) + each competitor URL
    (subject=competitor, competitor_name = hostname) into one bundle.

    Resilient: individual URL failures (timeouts, 4xx/5xx, DNS errors) are
    captured and SKIPPED — the cascade continues on whatever sources did
    scrape. Returns (bundle, errors). Each error is a dict
    {url, subject, error}. The on_error callback fires per failed URL so a
    worker can surface them as SSE events in real time.

    If EVERY URL fails the function raises RuntimeError — at that point
    there's nothing for the depts to read.

    The bundle's target field is the founder's business name; the rest of
    the cascade keys off it for prompts and the dashboard label.
    """
    sources: list[SourceItem] = []
    errors: list[dict] = []

    def _scrape(url: str, stype: SourceType, subject: SourceSubject,
                competitor_name: str = "") -> None:
        try:
            text = html_to_text(client.unlock(url))[:cap_chars]
        except Exception as exc:
            ev = {
                "url": url,
                "subject": subject.value,
                "competitor": competitor_name or None,
                "error": f"{type(exc).__name__}: {exc}",
            }
            errors.append(ev)
            if on_error is not None:
                try:
                    on_error(ev)
                except Exception:
                    pass
            return
        # post-scrape quality gate (V7.7) — drop bot-challenge pages, 404s,
        # access-denied responses, and pages so short they're almost
        # certainly empty/blocked. The LLM downstream has no way to detect
        # this so we catch it here before grounding wastes cycles on it.
        bad, reason = is_low_quality(text)
        if bad:
            ev = {
                "url": url,
                "subject": subject.value,
                "competitor": competitor_name or None,
                "error": f"low-quality response: {reason}",
            }
            errors.append(ev)
            if on_error is not None:
                try:
                    on_error(ev)
                except Exception:
                    pass
            return
        sources.append(
            SourceItem(
                source_type=stype,
                url=url,
                text=text,
                subject=subject,
                competitor_name=competitor_name,
            )
        )

    for url, stype in self_urls or []:
        _scrape(url, stype, SourceSubject.SELF)
    for url, stype in competitor_urls or []:
        _scrape(url, stype, SourceSubject.COMPETITOR, competitor_name=_hostname(url))

    if not sources:
        msg = "; ".join(f"{e['url']}: {e['error']}" for e in errors) or "no URLs supplied"
        raise RuntimeError(f"every URL failed to scrape — {msg}")

    return SharedBundle(target=business_name, sources=sources), errors
