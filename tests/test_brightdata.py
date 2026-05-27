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


def test_default_external_queries_includes_target_in_each():
    qs = default_external_queries("Supabase")
    assert len(qs) == 4
    for q, st in qs:
        assert "Supabase" in q
        assert isinstance(st, SourceType)


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
