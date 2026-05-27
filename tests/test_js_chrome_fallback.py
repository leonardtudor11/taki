"""V7.30 — JS-rendered SPA chrome detection + Wikipedia/Wayback fallback.

The Web Unlocker returns a navigation shell ("Skip to main content / You
need to enable JavaScript") for SPA targets (Pfizer.com, Notion.so).
That shell passes the existing is_low_quality gate (>150 chars, no
Cloudflare phrases) but starves every downstream agent. These tests pin
the detector + fallback wiring so the bundle picks up Wikipedia +
Wayback content automatically when chrome is detected.
"""

from __future__ import annotations

from agents.schemas import SourceType
from services.brightdata import (
    _wayback_url,
    _wikipedia_url,
    build_bundle,
    fetch_js_chrome_fallbacks,
    looks_like_js_chrome,
    trim_chrome_boilerplate,
)


# ─── pure detector ───────────────────────────────────────────────────────


def test_chrome_detector_flags_js_required_phrase():
    # JS-required phrase must land within the first 600 chars (head window).
    # Trail with bulk text so is_low_quality wouldn't catch it on its own.
    text = (
        "Pfizer Skip to main content "
        "You need to enable JavaScript to run this app. "
    ) + ("lorem ipsum " * 400)
    is_chrome, reason = looks_like_js_chrome(text)
    assert is_chrome
    assert "js-required" in reason


def test_chrome_detector_flags_thin_post_trim():
    # Just nav links — looks substantial raw but trims to a sliver.
    text = (
        "Skip to main content Toggle navigation Open menu Close menu "
        "Main menu Back to top " * 20
    ) + "Home About Contact"
    is_chrome, reason = looks_like_js_chrome(text)
    assert is_chrome
    assert "after trimming chrome" in reason


def test_chrome_detector_passes_real_content():
    # Real page: thousands of chars of body copy. Should NOT be flagged.
    text = "Acme Coffee Roasters delivers single-origin espresso to " \
        "subscribers across the EU. " * 200
    is_chrome, _ = looks_like_js_chrome(text)
    assert not is_chrome


def test_chrome_detector_handles_non_string():
    assert looks_like_js_chrome(None) == (False, "")
    assert looks_like_js_chrome(123) == (False, "")


def test_trim_chrome_boilerplate_strips_known_phrases():
    raw = "Skip to main content Toggle navigation hello world Loading..."
    trimmed = trim_chrome_boilerplate(raw)
    assert "skip to main content" not in trimmed.lower()
    assert "toggle navigation" not in trimmed.lower()
    assert "loading" not in trimmed.lower()
    assert "hello world" in trimmed


# ─── URL helpers ─────────────────────────────────────────────────────────


def test_wikipedia_url_slug_encoding():
    assert _wikipedia_url("Pfizer") == "https://en.wikipedia.org/wiki/Pfizer"
    assert _wikipedia_url("Notion Labs") == "https://en.wikipedia.org/wiki/Notion_Labs"
    # Non-ASCII percent-encoded but underscore preserved.
    url = _wikipedia_url("Société Générale")
    assert url.startswith("https://en.wikipedia.org/wiki/")
    assert "_" in url  # space → underscore before percent-encode


def test_wayback_url_format():
    snap = _wayback_url("https://pfizer.com/")
    assert snap == "https://web.archive.org/web/2025/https://pfizer.com/"


# ─── fallback fetch ──────────────────────────────────────────────────────


class _FakeClient:
    """Stub BrightDataClient.unlock — canned bodies per URL, records calls.

    `serp_zone` is set falsy so build_bundle skips the SERP step (tests
    drive their own URL list explicitly).
    """

    serp_zone = ""

    def __init__(self, bodies: dict[str, str]):
        self.bodies = bodies
        self.calls: list[str] = []

    def unlock(self, url: str) -> str:
        self.calls.append(url)
        if url not in self.bodies:
            raise RuntimeError(f"404 stub: {url}")
        return self.bodies[url]


def _real_body(stem: str, n: int = 60) -> str:
    """Generate a >150 char body that clears is_low_quality."""
    return f"<html><body>{('real ' + stem + ' content ') * n}</body></html>"


def _chrome_body() -> str:
    """JS-shell body that passes is_low_quality but trips the chrome detector."""
    return (
        "<html><body>Skip to main content Toggle navigation "
        "<p>You need to enable JavaScript to run this app.</p></body></html>"
    )


def test_fetch_fallbacks_returns_both_on_success():
    target = "Pfizer"
    chromed = "https://www.pfizer.com/"
    wiki = _wikipedia_url(target)
    wayback = _wayback_url(chromed)
    client = _FakeClient({
        wiki:    _real_body("wikipedia pfizer pharma"),
        wayback: _real_body("wayback pfizer snapshot"),
    })
    items = fetch_js_chrome_fallbacks(target, chromed, client)
    assert len(items) == 2
    assert {it.url for it in items} == {wiki, wayback}
    assert all(it.source_type == SourceType.SITE for it in items)


def test_fetch_fallbacks_skips_failures_silently():
    """Wikipedia 404 + Wayback success → only Wayback in result."""
    target = "ObscureCo"
    chromed = "https://obscure.co/"
    wayback = _wayback_url(chromed)
    client = _FakeClient({
        # No Wikipedia entry — _FakeClient raises for the wiki URL.
        wayback: _real_body("wayback obscure snapshot"),
    })
    events: list[dict] = []
    items = fetch_js_chrome_fallbacks(
        target, chromed, client, on_event=events.append,
    )
    assert len(items) == 1
    assert items[0].url == wayback
    # Wikipedia attempt should have emitted an 'error' event.
    assert any(e["status"] == "error" and e["kind"] == "wikipedia" for e in events)
    assert any(e["status"] == "ok"    and e["kind"] == "wayback"   for e in events)


def test_fetch_fallbacks_rejects_low_quality_response():
    """Wayback returns a calendar / 'snapshot not found' stub → dropped."""
    target = "Pfizer"
    chromed = "https://pfizer.com/"
    client = _FakeClient({
        _wikipedia_url(target): _real_body("wikipedia pfizer"),
        _wayback_url(chromed):  "<html><body>404</body></html>",  # too short
    })
    items = fetch_js_chrome_fallbacks(target, chromed, client)
    assert len(items) == 1
    assert "wikipedia" in items[0].url


# ─── build_bundle wiring ─────────────────────────────────────────────────


def test_build_bundle_triggers_fallback_on_chrome():
    target = "Pfizer"
    user_url = "https://www.pfizer.com/"
    wiki = _wikipedia_url(target)
    wayback = _wayback_url(user_url)
    client = _FakeClient({
        user_url: _chrome_body(),
        wiki:     _real_body("wikipedia pfizer body"),
        wayback:  _real_body("wayback pfizer body"),
    })
    # No serp_zone attribute on _FakeClient → falsy, SERP step skipped.
    chrome_events: list[dict] = []
    bundle = build_bundle(
        target=target,
        client=client,  # type: ignore[arg-type]
        urls=[(user_url, SourceType.SITE)],
        on_chrome=chrome_events.append,
    )
    urls_in_bundle = [s.url for s in bundle.sources]
    assert user_url in urls_in_bundle, "original chromed URL still kept"
    assert wiki    in urls_in_bundle, "wikipedia fallback appended"
    assert wayback in urls_in_bundle, "wayback fallback appended"
    # First event = chrome detection on the user URL; later events = fallback fetches.
    assert chrome_events[0]["url"] == user_url
    assert "reason" in chrome_events[0]


def test_build_bundle_skips_fallback_on_real_content():
    target = "Acme"
    user_url = "https://acme.coffee/"
    client = _FakeClient({user_url: _real_body("acme home content", n=120)})
    chrome_events: list[dict] = []
    bundle = build_bundle(
        target=target,
        client=client,  # type: ignore[arg-type]
        urls=[(user_url, SourceType.SITE)],
        on_chrome=chrome_events.append,
    )
    assert [s.url for s in bundle.sources] == [user_url]
    assert chrome_events == []
    # Wikipedia / Wayback URLs were never requested.
    assert _wikipedia_url(target) not in client.calls
    assert _wayback_url(user_url) not in client.calls


def test_build_bundle_chrome_fallback_disabled_param():
    """chrome_fallback=False skips the fallback even when chrome detected."""
    target = "Pfizer"
    user_url = "https://www.pfizer.com/"
    client = _FakeClient({user_url: _chrome_body()})
    bundle = build_bundle(
        target=target,
        client=client,  # type: ignore[arg-type]
        urls=[(user_url, SourceType.SITE)],
        chrome_fallback=False,
    )
    assert [s.url for s in bundle.sources] == [user_url]
    assert _wikipedia_url(target) not in client.calls


def test_build_bundle_fallback_fires_at_most_once():
    """Two chromed URLs → fallback runs ONCE (target is shared)."""
    target = "MegaCorp"
    u1 = "https://megacorp.com/"
    u2 = "https://megacorp.com/products"
    wiki    = _wikipedia_url(target)
    wayback = _wayback_url(u1)  # first chromed URL wins
    client = _FakeClient({
        u1:      _chrome_body(),
        u2:      _chrome_body(),
        wiki:    _real_body("megacorp wiki"),
        wayback: _real_body("megacorp wayback"),
    })
    bundle = build_bundle(
        target=target,
        client=client,  # type: ignore[arg-type]
        urls=[(u1, SourceType.SITE), (u2, SourceType.SITE)],
    )
    urls_in_bundle = [s.url for s in bundle.sources]
    # Both user URLs kept, plus exactly two fallbacks (wiki + first-url wayback).
    assert u1 in urls_in_bundle and u2 in urls_in_bundle
    assert wiki in urls_in_bundle
    assert wayback in urls_in_bundle
    # No second-url Wayback (only first chromed URL drives the fallback).
    assert _wayback_url(u2) not in urls_in_bundle
