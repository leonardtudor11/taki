"""V7.31 — target-mode sub-page discovery.

The self-mode concept-walk (`_expand` -> `discover_subpages`) is now
reused in `build_bundle` so a target-mode cascade (`run.py "Co" https://co.com`)
auto-pulls /about, /team, /pricing, /careers, /case-studies, /news,
/investors, /research, /blog, etc. — depth-pages the user never had to
list explicitly.

These tests pin the contract: the helper extracts cleanly, the target
URL drives expansion (not SERP-discovered externals), the chrome
fallback short-circuits expansion, and the legacy self-mode behaviour
still works after the refactor.
"""

from __future__ import annotations

from agents.schemas import SourceSubject, SourceType
from services.brightdata import (
    SUB_PAGE_GROUPS,
    build_bundle,
    build_self_bundle,
    discover_subpages,
)


def _real_body(stem: str, n: int = 120) -> str:
    # n>=120 keeps body text >1500 chars so the V7.30 chrome detector
    # treats it as real content (not a SPA shell) and lets the V7.31
    # sub-page expansion proceed in build_bundle tests.
    return f"<html><body>{('real ' + stem + ' content ') * n}</body></html>"


def _chrome_body() -> str:
    return (
        "<html><body>Skip to main content Toggle navigation "
        "<p>You need to enable JavaScript to run this app.</p></body></html>"
    )


class _FakeClient:
    """Stub BrightDataClient — canned per-URL bodies; missing URLs raise."""

    serp_zone = ""

    def __init__(self, bodies: dict[str, str]):
        self.bodies = bodies
        self.calls: list[str] = []

    def unlock(self, url: str) -> str:
        self.calls.append(url)
        if url not in self.bodies:
            raise RuntimeError(f"404 stub: {url}")
        return self.bodies[url]


# ─── new concepts in SUB_PAGE_GROUPS ─────────────────────────────────────


def test_sub_page_groups_includes_target_mode_concepts():
    """V7.31 added concepts that target-mode auto-discovery needs.
    Pin them so a refactor can't quietly drop one."""
    concept_names = {name for name, _ in SUB_PAGE_GROUPS}
    # legacy concepts (V7.12)
    assert {"about", "projects", "references", "products",
            "certifications", "news"} <= concept_names
    # new target-mode concepts (V7.31)
    assert {"team", "careers", "pricing", "investors",
            "research", "blog"} <= concept_names


def test_research_group_includes_sector_overlap_paths():
    """Pharma's /clinical-trials and academic SaaS /publications both
    flow through the research concept."""
    research = dict(SUB_PAGE_GROUPS)["research"]
    assert "/clinical-trials" in research
    assert "/publications" in research


# ─── discover_subpages helper ────────────────────────────────────────────


def test_discover_subpages_first_synonym_per_concept_wins():
    client = _FakeClient({
        "https://co.com/about":   _real_body("about page"),
        "https://co.com/team":    _real_body("team bios"),
        "https://co.com/pricing": _real_body("pricing tiers"),
    })
    found = discover_subpages(
        base_url="https://co.com/",
        client=client,  # type: ignore[arg-type]
    )
    found_urls = [it.url for it in found]
    assert "https://co.com/about"   in found_urls
    assert "https://co.com/team"    in found_urls
    assert "https://co.com/pricing" in found_urls
    # all returned items default to TARGET subject for target-mode use
    assert all(it.subject == SourceSubject.TARGET for it in found)


def test_discover_subpages_silent_on_misses():
    """No bodies registered for any concept synonym → empty result, no exception."""
    client = _FakeClient({})
    found = discover_subpages(
        base_url="https://obscure.co/",
        client=client,  # type: ignore[arg-type]
    )
    assert found == []
    # Helper attempted at least one URL per concept group.
    assert len(client.calls) > 0


def test_discover_subpages_respects_skip_urls():
    """URL already in skip set → concept treated as covered, helper
    breaks to next concept without calling unlock for it."""
    client = _FakeClient({
        "https://co.com/team": _real_body("team"),
    })
    skip = {"https://co.com/about"}  # caller says /about is already in bundle
    found = discover_subpages(
        base_url="https://co.com/",
        client=client,  # type: ignore[arg-type]
        skip_urls=skip,
    )
    # /about was NEVER requested — it was in skip from the start.
    assert "https://co.com/about" not in client.calls
    # /team still discovered.
    assert any(it.url == "https://co.com/team" for it in found)
    # /team appended to the shared skip set so callers can chain.
    assert "https://co.com/team" in skip


def test_discover_subpages_subject_and_competitor_name_threaded_through():
    client = _FakeClient({
        "https://rival.co/about": _real_body("rival about"),
    })
    found = discover_subpages(
        base_url="https://rival.co/",
        client=client,  # type: ignore[arg-type]
        subject=SourceSubject.COMPETITOR,
        competitor_name="rival.co",
    )
    assert len(found) == 1
    assert found[0].subject == SourceSubject.COMPETITOR
    assert found[0].competitor_name == "rival.co"


def test_discover_subpages_on_discover_fires_per_hit():
    client = _FakeClient({
        "https://co.com/about":   _real_body("about"),
        "https://co.com/pricing": _real_body("pricing"),
    })
    events: list[dict] = []
    discover_subpages(
        base_url="https://co.com/",
        client=client,  # type: ignore[arg-type]
        on_discover=events.append,
    )
    concepts_hit = {e["concept"] for e in events}
    assert "about"   in concepts_hit
    assert "pricing" in concepts_hit
    # one event per hit (not per attempt)
    assert len(events) == len(concepts_hit)


# ─── build_bundle target-mode wiring ─────────────────────────────────────


def test_build_bundle_expands_first_user_url_by_default():
    target = "Acme"
    home = "https://acme.co/"
    client = _FakeClient({
        home:                        _real_body("acme home", n=120),
        "https://acme.co/about":     _real_body("about"),
        "https://acme.co/pricing":   _real_body("pricing"),
        "https://acme.co/careers":   _real_body("careers"),
    })
    events: list[dict] = []
    bundle = build_bundle(
        target=target,
        client=client,  # type: ignore[arg-type]
        urls=[(home, SourceType.SITE)],
        on_discover=events.append,
    )
    urls_in_bundle = {s.url for s in bundle.sources}
    assert "https://acme.co/about"   in urls_in_bundle
    assert "https://acme.co/pricing" in urls_in_bundle
    assert "https://acme.co/careers" in urls_in_bundle
    # SSE-style discover events fired
    assert {e["concept"] for e in events} >= {"about", "pricing", "careers"}


def test_build_bundle_expand_url_overrides_first_url():
    """When server passes expand_url explicitly (e.g. user_urls[0][0]),
    SERP-discovered URLs prepended to the list MUST NOT drive expansion."""
    target = "Acme"
    home = "https://acme.co/"
    external_news = "https://news.example/coverage"
    client = _FakeClient({
        home:                        _real_body("acme home"),
        external_news:               _real_body("news article"),
        # NEWS site has an /about page — without expand_url override we'd
        # incorrectly expand news.example.com.
        "https://news.example/about": _real_body("news org about"),
        # Real expansion target (acme.co) has /pricing.
        "https://acme.co/pricing":   _real_body("pricing"),
    })
    # Pass URLs as the server does: [external] + [user] — but pin expand_url.
    bundle = build_bundle(
        target=target,
        client=client,  # type: ignore[arg-type]
        urls=[(external_news, SourceType.NEWS), (home, SourceType.SITE)],
        expand_url=home,
    )
    urls_in_bundle = {s.url for s in bundle.sources}
    assert "https://acme.co/pricing"   in urls_in_bundle, "acme expanded"
    assert "https://news.example/about" not in urls_in_bundle, "news.example NOT expanded"


def test_build_bundle_expand_subpages_disabled():
    target = "Acme"
    home = "https://acme.co/"
    client = _FakeClient({
        home:                       _real_body("acme home"),
        "https://acme.co/about":    _real_body("about"),
        "https://acme.co/pricing":  _real_body("pricing"),
    })
    bundle = build_bundle(
        target=target,
        client=client,  # type: ignore[arg-type]
        urls=[(home, SourceType.SITE)],
        expand_subpages=False,
    )
    urls_in_bundle = {s.url for s in bundle.sources}
    assert urls_in_bundle == {home}
    # No sub-page URLs were ever requested.
    assert "https://acme.co/about"   not in client.calls
    assert "https://acme.co/pricing" not in client.calls


def test_build_bundle_skips_expansion_when_primary_chromed():
    """A JS-chrome primary page yields chrome sub-pages too — expansion
    would burn Unlocker credit for no signal. Skip it."""
    target = "Pfizer"
    home = "https://pfizer.com/"
    client = _FakeClient({
        home:                          _chrome_body(),
        # Fallback URLs registered so chrome-fallback path completes.
        "https://en.wikipedia.org/wiki/Pfizer":         _real_body("wiki pfizer"),
        "https://web.archive.org/web/2025/" + home:     _real_body("wayback pfizer"),
        # Sub-pages exist (would be expanded) but expansion must be skipped.
        "https://pfizer.com/about":    _real_body("about"),
        "https://pfizer.com/pricing":  _real_body("pricing"),
    })
    bundle = build_bundle(
        target=target,
        client=client,  # type: ignore[arg-type]
        urls=[(home, SourceType.SITE)],
    )
    urls_in_bundle = {s.url for s in bundle.sources}
    # Chrome fallback fired — wiki + wayback in bundle.
    assert "https://en.wikipedia.org/wiki/Pfizer" in urls_in_bundle
    # Sub-page discovery did NOT fire — /about and /pricing absent.
    assert "https://pfizer.com/about"   not in urls_in_bundle
    assert "https://pfizer.com/pricing" not in urls_in_bundle
    # And those URLs were never requested.
    assert "https://pfizer.com/about"   not in client.calls
    assert "https://pfizer.com/pricing" not in client.calls


def test_build_bundle_dedupes_user_url_against_concept_synonym():
    """User explicitly passes /about — concept walker should NOT re-scrape it."""
    target = "Acme"
    home = "https://acme.co/"
    about = "https://acme.co/about"
    client = _FakeClient({
        home:                       _real_body("home"),
        about:                      _real_body("about"),
        "https://acme.co/pricing":  _real_body("pricing"),
    })
    bundle = build_bundle(
        target=target,
        client=client,  # type: ignore[arg-type]
        urls=[(home, SourceType.SITE), (about, SourceType.SITE)],
    )
    # /about only scraped once (the user-supplied request); the
    # discover_subpages about-group should have seen it in skip and bailed.
    assert client.calls.count(about) == 1
    # Other concepts still discovered.
    urls_in_bundle = {s.url for s in bundle.sources}
    assert "https://acme.co/pricing" in urls_in_bundle


# ─── build_self_bundle refactor regression ────────────────────────────────


def test_build_self_bundle_after_refactor_still_expands():
    """Sanity: self-mode _expand now delegates to discover_subpages.
    Existing self-mode behaviour (expand_self default True, first URL,
    silent misses) must keep working."""
    client = _FakeClient({
        "https://me.co/":          _real_body("home"),
        "https://me.co/about":     _real_body("about me"),
        "https://me.co/projects":  _real_body("our work"),
    })
    discovered: list[dict] = []
    bundle, errors = build_self_bundle(
        business_name="Me",
        self_urls=[("https://me.co/", SourceType.SITE)],
        competitor_urls=[],
        client=client,  # type: ignore[arg-type]
        on_discover=discovered.append,
    )
    urls_in_bundle = {s.url for s in bundle.sources}
    assert "https://me.co/"         in urls_in_bundle
    assert "https://me.co/about"    in urls_in_bundle
    assert "https://me.co/projects" in urls_in_bundle
    assert errors == []  # sub-page misses silent
    # SELF subject preserved through the refactor
    discovered_items = [s for s in bundle.sources if s.url != "https://me.co/"]
    assert all(it.subject == SourceSubject.SELF for it in discovered_items)
    concepts_hit = {e["concept"] for e in discovered}
    assert "about"    in concepts_hit
    assert "projects" in concepts_hit
