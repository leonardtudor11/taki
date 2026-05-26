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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _request(self, zone: str, url: str, fmt: str = "raw") -> str:
        self.tracker.charge()
        resp = httpx.post(
            _API,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=build_payload(zone, url, fmt),
            timeout=90,
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
) -> SharedBundle:
    """Scrape the founder's own URLs (subject=self) + each competitor URL
    (subject=competitor, competitor_name = hostname) into one bundle.

    The bundle's target field is the founder's business name — the rest of the
    cascade keys off it for prompts and the dashboard label.
    """
    sources: list[SourceItem] = []
    for url, stype in self_urls or []:
        sources.append(
            SourceItem(
                source_type=stype,
                url=url,
                text=html_to_text(client.unlock(url))[:cap_chars],
                subject=SourceSubject.SELF,
            )
        )
    for url, stype in competitor_urls or []:
        sources.append(
            SourceItem(
                source_type=stype,
                url=url,
                text=html_to_text(client.unlock(url))[:cap_chars],
                subject=SourceSubject.COMPETITOR,
                competitor_name=_hostname(url),
            )
        )
    return SharedBundle(target=business_name, sources=sources)
