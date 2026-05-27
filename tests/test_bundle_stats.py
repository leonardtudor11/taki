"""V7.37 — Bundle stats computation tests.

Pins the contract for _compute_bundle_stats: tier counts derived from
the URL host via services.brightdata.classify_url, subject + source_type
counts from each SourceItem field, sub-page heuristic from URL path
depth, chrome fallback heuristic from wikipedia.org / web.archive.org
hosts, expert quote count threaded in.
"""

from __future__ import annotations

from agents.cascade_graph import _compute_bundle_stats
from agents.schemas import BundleStats, SharedBundle, SourceItem, SourceSubject, SourceType


def _item(url: str, st: SourceType = SourceType.SITE,
          subj: SourceSubject = SourceSubject.TARGET) -> SourceItem:
    return SourceItem(source_type=st, url=url, text="body " * 80, subject=subj)


def test_returns_empty_stats_for_empty_bundle():
    out = _compute_bundle_stats(None)
    assert isinstance(out, BundleStats)
    assert out.sources_total == 0
    assert out.by_tier == {}
    assert out.expert_quote_count == 0


def test_tier_counts_from_classify_url():
    bundle = SharedBundle(target="X", sources=[
        _item("https://www.fda.gov/some/page"),                    # T1
        _item("https://arxiv.org/abs/2024.01234"),                 # T2
        _item("https://www.reuters.com/business/x"),               # T3
        _item("https://reddit.com/r/saas/comments/x"),             # T5
        _item("https://acme-randomvendor.example/about"),          # T0 unknown
    ])
    out = _compute_bundle_stats(bundle)
    assert out.sources_total == 5
    assert out.by_tier.get("T1") == 1
    assert out.by_tier.get("T2") == 1
    assert out.by_tier.get("T3") == 1
    assert out.by_tier.get("T5") == 1
    assert out.by_tier.get("T0") == 1


def test_subject_and_source_type_counts():
    bundle = SharedBundle(target="X", sources=[
        _item("https://acme.co/",         st=SourceType.SITE,    subj=SourceSubject.TARGET),
        _item("https://acme.co/pricing",  st=SourceType.PRICING, subj=SourceSubject.TARGET),
        _item("https://rival.co/",        st=SourceType.SITE,    subj=SourceSubject.COMPETITOR),
        _item("https://news.example/x",   st=SourceType.NEWS,    subj=SourceSubject.TARGET),
    ])
    out = _compute_bundle_stats(bundle)
    assert out.by_subject.get("target") == 3
    assert out.by_subject.get("competitor") == 1
    assert out.by_source_type.get("site") == 2
    assert out.by_source_type.get("pricing") == 1
    assert out.by_source_type.get("news") == 1


def test_chrome_fallback_count_from_wikipedia_and_wayback():
    bundle = SharedBundle(target="Pfizer", sources=[
        _item("https://www.pfizer.com/"),  # primary
        _item("https://en.wikipedia.org/wiki/Pfizer"),
        _item("https://web.archive.org/web/2025/https://www.pfizer.com/"),
    ])
    out = _compute_bundle_stats(bundle)
    assert out.chrome_fallbacks == 2
    # The Wikipedia + Wayback URLs are SITE-typed but should NOT be
    # counted as sub-pages (chrome detection takes precedence).
    assert out.expanded_subpages == 0


def test_subpage_count_from_path_depth():
    bundle = SharedBundle(target="X", sources=[
        _item("https://acme.co/",          subj=SourceSubject.TARGET),  # root, not a sub-page
        _item("https://acme.co/about",     subj=SourceSubject.TARGET),  # depth 1, IS sub-page
        _item("https://acme.co/pricing",   subj=SourceSubject.TARGET),  # IS sub-page
        _item("https://acme.co/blog/post", subj=SourceSubject.TARGET),  # IS sub-page (deeper)
    ])
    out = _compute_bundle_stats(bundle)
    # Heuristic: SITE + target + url.count('/') > 3 (https://host/path = 3 slashes)
    assert out.expanded_subpages == 3


def test_subpage_count_ignores_competitor_subject():
    """Sub-page discovery only fires on target's own domain — competitor
    sub-pages shouldn't inflate the expanded_subpages count."""
    bundle = SharedBundle(target="X", sources=[
        _item("https://rival.co/about",   subj=SourceSubject.COMPETITOR),
        _item("https://rival.co/pricing", subj=SourceSubject.COMPETITOR),
    ])
    out = _compute_bundle_stats(bundle)
    assert out.expanded_subpages == 0


def test_expert_quote_count_threaded_through():
    bundle = SharedBundle(target="X", sources=[_item("https://x.com/")])
    out = _compute_bundle_stats(bundle, expert_quote_count=7)
    assert out.expert_quote_count == 7


def test_handles_empty_url_with_t0_tier():
    bundle = SharedBundle(target="X", sources=[
        SourceItem(source_type=SourceType.OTHER, url="", text="some body " * 30),
    ])
    out = _compute_bundle_stats(bundle)
    assert out.sources_total == 1
    assert out.by_tier.get("T0") == 1
