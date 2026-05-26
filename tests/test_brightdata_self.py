"""V7.2 — build_self_bundle resilience: per-URL failures don't kill the bundle.

The previous behaviour (raise on first scrape failure) made self-mode brittle
— one bad competitor URL hung or crashed the whole cascade. Now each URL is
tried independently, errors surface to an on_error callback + the returned
errors list, and the cascade continues with whatever scraped.
"""

import pytest

from agents.schemas import SourceSubject, SourceType
from services.brightdata import _hostname, build_self_bundle


class _FakeClient:
    def __init__(self, by_url: dict):
        self.by_url = by_url   # url -> ("ok", html) or ("err", message)
        self.calls = []

    def unlock(self, url: str) -> str:
        self.calls.append(url)
        kind, payload = self.by_url.get(url, ("err", "url not configured"))
        if kind == "err":
            raise RuntimeError(payload)
        return payload


def test_hostname_strips_www():
    assert _hostname("https://www.stripe.com/pricing") == "stripe.com"
    assert _hostname("http://blue-bottle.com/") == "blue-bottle.com"
    assert _hostname("invalid url") == "invalid url"


def test_build_self_bundle_skips_failed_urls():
    # body text must be > 150 chars to clear the V7.7 quality gate
    my_body = "we sell beans to offices — coffee, cold brew, single origin, " * 6
    comp_body = "we sell ground beans cheaper than the competition — wholesale, retail, " * 6
    client = _FakeClient({
        "https://me.example/":         ("ok", f"<html><body>{my_body}</body></html>"),
        "https://good-comp.example/":  ("ok", f"<html><body>{comp_body}</body></html>"),
        "https://bad-comp.example/":   ("err", "BD timeout"),
    })
    errors_captured = []

    bundle, errors = build_self_bundle(
        business_name="Me",
        self_urls=[("https://me.example/", SourceType.SITE)],
        competitor_urls=[
            ("https://good-comp.example/", SourceType.SITE),
            ("https://bad-comp.example/",  SourceType.SITE),
        ],
        client=client,
        on_error=errors_captured.append,
    )

    # only the 2 successful URLs land in the bundle
    assert len(bundle.sources) == 2
    subjects = {s.subject for s in bundle.sources}
    assert subjects == {SourceSubject.SELF, SourceSubject.COMPETITOR}

    # the failure is surfaced both in the returned list and the callback
    assert len(errors) == 1
    assert errors[0]["url"] == "https://bad-comp.example/"
    assert "BD timeout" in errors[0]["error"]
    assert errors == errors_captured


def test_build_self_bundle_raises_when_all_fail():
    client = _FakeClient({
        "https://a.example/": ("err", "DNS NXDOMAIN"),
        "https://b.example/": ("err", "503"),
    })
    with pytest.raises(RuntimeError) as exc:
        build_self_bundle(
            business_name="Me",
            self_urls=[("https://a.example/", SourceType.SITE)],
            competitor_urls=[("https://b.example/", SourceType.SITE)],
            client=client,
        )
    assert "every URL failed to scrape" in str(exc.value)


def test_build_self_bundle_rejects_low_quality_text():
    """A scraped URL that returns an error page (e.g. CF challenge) should be
    rejected by the post-scrape quality gate, not let into the bundle."""
    client = _FakeClient({
        "https://me.example/":     ("ok", "<html><body>" + ("real content " * 30) + "</body></html>"),
        "https://blocked.example/": ("ok", "<html><body>Just a moment — checking your browser before accessing.</body></html>"),
    })
    bundle, errors = build_self_bundle(
        business_name="Me",
        self_urls=[("https://me.example/", SourceType.SITE)],
        competitor_urls=[("https://blocked.example/", SourceType.SITE)],
        client=client,
    )
    # only the real-content URL lands in the bundle
    assert len(bundle.sources) == 1
    assert bundle.sources[0].subject == SourceSubject.SELF
    # the blocked URL surfaces as an error with a quality reason
    assert len(errors) == 1
    assert "low-quality" in errors[0]["error"]


def test_build_self_bundle_competitor_name_set():
    # again, body must pass the post-scrape quality gate
    me = "this is my real homepage with a clear value proposition for buyers, " * 4
    them = "this is the competitor homepage with their own value proposition and pricing, " * 4
    client = _FakeClient({
        "https://me.example/":              ("ok", f"<html>{me}</html>"),
        "https://www.competitor.io/page":   ("ok", f"<html>{them}</html>"),
    })
    bundle, _ = build_self_bundle(
        business_name="Me",
        self_urls=[("https://me.example/", SourceType.SITE)],
        competitor_urls=[("https://www.competitor.io/page", SourceType.SITE)],
        client=client,
    )
    comp_sources = [s for s in bundle.sources if s.subject == SourceSubject.COMPETITOR]
    assert len(comp_sources) == 1
    assert comp_sources[0].competitor_name == "competitor.io"
