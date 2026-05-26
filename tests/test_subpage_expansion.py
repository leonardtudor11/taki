"""V7.12 — auto-discover sub-pages: per-concept synonym walk, first success wins."""

from agents.schemas import SourceSubject, SourceType
from services.brightdata import (
    SUB_PAGE_GROUPS,
    _site_root,
    build_self_bundle,
)


class _FakeClient:
    """Minimal Bright Data client that returns canned bodies per URL."""
    def __init__(self, by_url: dict):
        self.by_url = by_url
        self.calls: list[str] = []

    def unlock(self, url: str) -> str:
        self.calls.append(url)
        kind, payload = self.by_url.get(url, ("err", "404 — not configured"))
        if kind == "err":
            raise RuntimeError(payload)
        return payload


def _real_body(stem: str) -> str:
    return f"<html><body>{('real ' + stem + ' content ') * 30}</body></html>"


def test_site_root_strips_path_and_query():
    assert _site_root("https://acme.coffee/pricing?utm=x") == "https://acme.coffee"
    assert _site_root("https://www.example.com/a/b/")     == "https://www.example.com"


def test_expand_picks_first_concept_synonym_that_passes():
    """Site has /about (first synonym in the 'about' group) AND /our-story (later in
    group) — _expand should keep the FIRST hit per concept group and not spam
    the second synonym."""
    client = _FakeClient({
        "https://acme.coffee/":           ("ok", _real_body("home")),
        "https://acme.coffee/about":      ("ok", _real_body("about us")),
        "https://acme.coffee/our-story":  ("ok", _real_body("our story")),
        # /about-us has nothing; /about already won the concept so /about-us
        # should never be requested.
    })
    discovered: list[dict] = []
    bundle, errors = build_self_bundle(
        business_name="Acme",
        self_urls=[("https://acme.coffee/", SourceType.SITE)],
        competitor_urls=[],
        client=client,
        on_discover=discovered.append,
    )
    # the bundle has the homepage + /about (about-group winner)
    urls = [s.url for s in bundle.sources]
    assert "https://acme.coffee/" in urls
    assert "https://acme.coffee/about" in urls
    # we never tried /our-story or /about-us because /about satisfied the group
    assert "https://acme.coffee/our-story" not in client.calls
    # discovery event fired once for /about
    assert any(d["concept"] == "about" and d["url"].endswith("/about") for d in discovered)


def test_expand_skips_concept_when_all_synonyms_fail():
    """No /about variant resolves — concept silently skipped, no error log
    pollution. Other concepts still try."""
    client = _FakeClient({
        "https://acme.coffee/":            ("ok", _real_body("home")),
        "https://acme.coffee/projects":    ("ok", _real_body("our projects")),
        # nothing for the about-group → silently skipped
    })
    errors_pre = []
    bundle, errors = build_self_bundle(
        business_name="Acme",
        self_urls=[("https://acme.coffee/", SourceType.SITE)],
        competitor_urls=[],
        client=client,
        on_error=errors_pre.append,
    )
    urls = [s.url for s in bundle.sources]
    assert "https://acme.coffee/projects" in urls
    # silent — sub-page misses are NOT in the user-facing errors list
    assert errors == []
    assert errors_pre == []


def test_expand_off_keeps_legacy_behaviour():
    """expand_self=False reverts to scraping only the user-supplied URLs."""
    client = _FakeClient({
        "https://acme.coffee/":         ("ok", _real_body("home")),
        "https://acme.coffee/about":    ("ok", _real_body("about us")),
    })
    bundle, _ = build_self_bundle(
        business_name="Acme",
        self_urls=[("https://acme.coffee/", SourceType.SITE)],
        competitor_urls=[],
        client=client,
        expand_self=False,
    )
    urls = [s.url for s in bundle.sources]
    assert urls == ["https://acme.coffee/"]
    # /about was never tried
    assert "https://acme.coffee/about" not in client.calls


def test_expand_only_runs_for_self_url_not_competitors():
    """Competitor URLs stay as the user typed — auto-expansion is self-only."""
    client = _FakeClient({
        "https://me.example/":              ("ok", _real_body("my home")),
        "https://me.example/about":         ("ok", _real_body("about me")),
        "https://competitor.io/":           ("ok", _real_body("their home")),
        "https://competitor.io/about":      ("ok", _real_body("about them")),
    })
    bundle, _ = build_self_bundle(
        business_name="Me",
        self_urls=[("https://me.example/", SourceType.SITE)],
        competitor_urls=[("https://competitor.io/", SourceType.SITE)],
        client=client,
    )
    competitor_subs = [
        s for s in bundle.sources if s.subject == SourceSubject.COMPETITOR
    ]
    # only the homepage of competitor.io is in the bundle — /about was not tried
    assert len(competitor_subs) == 1
    assert competitor_subs[0].url == "https://competitor.io/"
    assert "https://competitor.io/about" not in client.calls


def test_sub_page_groups_cover_the_concepts_we_promise():
    """Smoke-test the concept registry so a refactor can't quietly drop a
    concept the README + JOURNEY mention."""
    concept_names = {name for name, _ in SUB_PAGE_GROUPS}
    assert {"about", "projects", "references", "products",
            "certifications", "news"} <= concept_names
