import pytest

from services.brightdata import (
    BrightDataClient,
    BudgetExceeded,
    SpendTracker,
    build_payload,
    html_to_text,
)


def test_payload_shape():
    assert build_payload("z", "https://x.com") == {
        "zone": "z",
        "url": "https://x.com",
        "format": "raw",
    }


def test_html_to_text_strips_tags_and_scripts():
    html = "<html><script>var x=1;</script><p>Hello  <b>world</b></p></html>"
    assert html_to_text(html) == "Hello world"


def test_spend_tracker_enforces_cap():
    t = SpendTracker(cap_usd=0.0025, cost_per_request=0.001)
    t.charge()
    t.charge()
    with pytest.raises(BudgetExceeded):
        t.charge()  # third would hit 0.003 > 0.0025


def test_client_requires_key(monkeypatch):
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        BrightDataClient()


# ─── V7.22 — SERP-based external source discovery ────────────────────────

from services.brightdata import (
    _clean_serp_url,
    default_external_queries,
    discover_external_sources,
    parse_serp_results,
)
from agents.schemas import SourceType


def test_clean_serp_url_strips_text_fragments():
    assert _clean_serp_url("https://x.com/page#:~:text=foo") == "https://x.com/page"
    assert _clean_serp_url("https://x.com/page#section") == "https://x.com/page"
    # bare-host trailing slash preserved (it's the canonical root URL)
    assert _clean_serp_url("https://x.com/") == "https://x.com/"
    # deeper trailing slash dropped for consistent dedup
    assert _clean_serp_url("https://x.com/foo/bar/") == "https://x.com/foo/bar"


def test_parse_serp_results_filters_google_internals():
    html = '''
      <a href="https://google.com/something">google</a>
      <a href="https://www.gstatic.com/x.png">gstatic</a>
      <a href="https://youtube.com/watch?v=x">yt</a>
      <a href="https://realsite.com/article">real</a>
      <a href="https://blog.example/post">blog</a>
    '''
    urls = parse_serp_results(html, exclude_hosts=set())
    assert "https://realsite.com/article" in urls
    assert "https://blog.example/post" in urls
    assert not any("google" in u or "gstatic" in u or "youtube" in u for u in urls)


def test_parse_serp_results_excludes_target_domain():
    html = '''
      <a href="https://supabase.com/">target</a>
      <a href="https://docs.supabase.com/page">target subdomain</a>
      <a href="https://reddit.com/r/Supabase/x">community</a>
      <a href="https://hackernews.com/item">news</a>
    '''
    urls = parse_serp_results(html, exclude_hosts={"supabase.com"})
    assert not any("supabase.com" in u for u in urls)
    assert "https://reddit.com/r/Supabase/x" in urls


def test_parse_serp_results_dedupes_after_fragment_strip():
    html = '''
      <a href="https://x.com/article">a</a>
      <a href="https://x.com/article#:~:text=foo">a-frag</a>
      <a href="https://x.com/article#section">a-hash</a>
    '''
    urls = parse_serp_results(html, exclude_hosts=set())
    assert urls.count("https://x.com/article") == 1


def test_parse_serp_results_unwraps_google_redirect_prefix():
    """Older SERP layouts wrapped results in /url?q=https://real..."""
    html = '<a href="/url?q=https://real-site.com/page">x</a>'
    urls = parse_serp_results(html, exclude_hosts=set())
    assert urls == ["https://real-site.com/page"]


def test_parse_serp_results_respects_max_urls():
    html = "".join(f'<a href="https://h{i}.example/x">{i}</a>' for i in range(20))
    urls = parse_serp_results(html, exclude_hosts=set(), max_urls=5)
    assert len(urls) == 5


def test_default_external_queries_base_layer_always_present():
    """Even with no industry, base layer (filings/news/scholar) fires."""
    qs = default_external_queries("Supabase")
    # base layer + fallback layer = 7 queries
    assert len(qs) == 7
    base_q = [q for q,_ in qs[:3]]
    assert any("filetype:pdf" in q and "annual report" in q for q in base_q)
    assert any("Financial Times" in q for q in base_q)
    assert any("scholar.google.com" in q for q in base_q)


def test_default_external_queries_industry_wind_energy():
    """Wind-energy industry triggers IRENA + Wind Power Monthly + EU Green Deal."""
    qs = default_external_queries("Orchid SRL", industry="wind turbines", region="Romania")
    all_q = " ".join(q for q,_ in qs)
    assert "IRENA" in all_q
    assert "Wind Power Monthly" in all_q or "WindEurope" in all_q
    assert "EU Green Deal" in all_q
    # region expansion
    assert "Eastern Europe" in all_q or "Romania" in all_q


def test_default_external_queries_industry_backend_saas():
    qs = default_external_queries("Supabase", industry="backend-as-a-service", region="US")
    all_q = " ".join(q for q,_ in qs)
    assert "Gartner" in all_q or "Forrester" in all_q
    assert "backend-as-a-service" in all_q or "market size" in all_q


def test_default_external_queries_unknown_industry_falls_back():
    """Industry that doesn't match any template uses the V7.22 generic queries."""
    qs = default_external_queries("Anything", industry="zigzag widgets")
    all_q = " ".join(q for q,_ in qs)
    # generic fallback
    assert "review OR critique" in all_q
    assert "funding" in all_q or "outage" in all_q


def test_discover_external_sources_emits_events_and_dedupes():
    """Stub out client.unlock to return canned HTML for each query;
    confirm on_event fires + cross-query URL dedup works."""

    class StubClient:
        def unlock(self, url):
            return '''
              <a href="https://reddit.com/r/foo/thread1">r1</a>
              <a href="https://reddit.com/r/foo/thread1">dup</a>
              <a href="https://news.example/article">n1</a>
            '''

    events = []
    queries = [
        ("Foo review", SourceType.REVIEW),
        ("Foo funding", SourceType.NEWS),
    ]
    out = discover_external_sources(
        target="Foo",
        client=StubClient(),
        queries=queries,
        exclude_hosts=["foo.com"],
        n_per_query=3,
        on_event=events.append,
    )
    urls = [u for u, _ in out]
    assert len(urls) == len(set(urls)), "expected dedup across queries"
    assert any(e.get("status") == "serp_done" for e in events)
    assert any(e.get("status") == "serp_start" for e in events)


# ─── V7.26 — Source-tier classifier ──────────────────────────────────────

from services.brightdata import (
    T1_REGULATOR, T2_ACADEMIC, T3_NEWS, T4_TRADE, T5_COMMUNITY, T6_REVIEW,
    T0_UNKNOWN, classify_url,
)


def test_classify_url_regulator_t1():
    assert classify_url("https://www.sec.gov/Archives/edgar/data/foo.pdf") == T1_REGULATOR
    assert classify_url("https://eur-lex.europa.eu/legal-content/EN/x") == T1_REGULATOR
    assert classify_url("https://www.iea.org/reports/wind-2024") == T1_REGULATOR
    assert classify_url("https://irena.org/publications/2025") == T1_REGULATOR
    assert classify_url("https://www.gov.uk/government/publications/x") == T1_REGULATOR


def test_classify_url_academic_t2():
    assert classify_url("https://scholar.google.com/scholar?q=wind") == T2_ACADEMIC
    assert classify_url("https://www.nature.com/articles/x") == T2_ACADEMIC
    assert classify_url("https://arxiv.org/abs/2401.12345") == T2_ACADEMIC
    assert classify_url("https://mit.edu/research/x") == T2_ACADEMIC


def test_classify_url_news_t3():
    assert classify_url("https://www.ft.com/content/x") == T3_NEWS
    assert classify_url("https://www.bloomberg.com/news/articles/x") == T3_NEWS
    assert classify_url("https://www.reuters.com/business/x") == T3_NEWS
    assert classify_url("https://www.gartner.com/en/research/x") == T3_NEWS


def test_classify_url_trade_t4():
    assert classify_url("https://techcrunch.com/2025/funding") == T4_TRADE
    assert classify_url("https://www.windpowermonthly.com/x") == T4_TRADE
    assert classify_url("https://www.redmonk.com/post") == T4_TRADE


def test_classify_url_community_t5():
    assert classify_url("https://www.reddit.com/r/Supabase/x") == T5_COMMUNITY
    assert classify_url("https://news.ycombinator.com/item?id=1") == T5_COMMUNITY
    assert classify_url("https://medium.com/@user/post") == T5_COMMUNITY


def test_classify_url_review_t6():
    assert classify_url("https://www.g2.com/products/x") == T6_REVIEW
    assert classify_url("https://www.trustpilot.com/review/x") == T6_REVIEW
    assert classify_url("https://www.glassdoor.com/Overview/x") == T6_REVIEW


def test_classify_url_blocked():
    assert classify_url("https://random.blogspot.com/post") == "BLOCKED"
    assert classify_url("https://facebook.com/page") == "BLOCKED"


def test_classify_url_unknown():
    assert classify_url("https://random-no-tier-site.com/x") == T0_UNKNOWN
    assert classify_url("not-a-url") == T0_UNKNOWN
    assert classify_url("") == T0_UNKNOWN


def test_discover_caps_low_tier_share():
    """When SERP returns mostly Reddit, the cap kicks in and most Reddit
    URLs get dropped while T1-T4 are preserved."""
    class StubClient:
        def __init__(self):
            self.n = 0
        def unlock(self, url):
            # return a mix: 1 IRENA (T1), 1 FT (T3), 4 Reddit (T5)
            self.n += 1
            return f'''
              <a href="https://irena.org/report-{self.n}">x</a>
              <a href="https://www.ft.com/article-{self.n}">x</a>
              <a href="https://www.reddit.com/r/foo/{self.n}a">x</a>
              <a href="https://www.reddit.com/r/foo/{self.n}b">x</a>
              <a href="https://www.reddit.com/r/foo/{self.n}c">x</a>
              <a href="https://www.reddit.com/r/foo/{self.n}d">x</a>
            '''

    events = []
    out = discover_external_sources(
        target="X",
        client=StubClient(),
        queries=[("q1", SourceType.NEWS)],
        exclude_hosts=[],
        n_per_query=6,
        on_event=events.append,
        low_tier_cap=0.30,
    )
    urls = [u for u,_ in out]
    n_reddit = sum(1 for u in urls if "reddit" in u)
    n_total = len(urls)
    # cap is 30% of total — Reddit shouldn't dominate
    assert n_reddit <= max(1, int(n_total * 0.30) + 1), \
        f"Reddit slipped past cap: {n_reddit}/{n_total}"
    # T1 (IRENA) and T3 (FT) preserved
    assert any("irena.org" in u for u in urls)
    assert any("ft.com" in u for u in urls)
    # event stream contains the tier_summary
    assert any(e.get("status") == "tier_summary" for e in events)


def test_discover_external_sources_swallows_per_query_errors():
    """One flaky SERP query shouldn't abort the whole pass — emit error
    event and keep going."""
    class FlakyClient:
        def __init__(self):
            self.calls = 0
        def unlock(self, url):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("boom")
            return '<a href="https://ok.example/page">ok</a>'

    events = []
    out = discover_external_sources(
        target="X",
        client=FlakyClient(),
        queries=[("q1", SourceType.NEWS), ("q2", SourceType.REVIEW)],
        n_per_query=2,
        on_event=events.append,
    )
    assert any(e.get("status") == "serp_error" for e in events)
    # second query still produced a result
    assert any(u == "https://ok.example/page" for u, _ in out)
