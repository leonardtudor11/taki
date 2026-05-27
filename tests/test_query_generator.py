"""V7.36 — Dynamic LLM-driven SERP query generator tests."""

from __future__ import annotations

import json

from agents import query_generator
from agents.schemas import SourceType


def _llm_returning(queries: list[dict]) -> callable:
    def _fn(_p):
        return json.dumps({"queries": queries})
    return _fn


def test_returns_empty_when_industry_empty():
    assert query_generator.generate_queries(
        target="Acme", industry="", llm=lambda _p: '{"queries":[{"query":"x","source_type":"news"}]}',
    ) == []


def test_returns_typed_query_tuples():
    llm = _llm_returning([
        {"query": '"Acme" UL Listed inverter 2024',  "source_type": "news"},
        {"query": '"Acme" NEVI federal funding award', "source_type": "news"},
        {"query": '"Acme" Hacker News discussion',    "source_type": "review"},
    ])
    out = query_generator.generate_queries(
        target="Acme", industry="EV charging hardware", llm=llm,
    )
    assert len(out) == 3
    assert all(isinstance(q, str) and isinstance(st, SourceType) for q, st in out)
    assert out[0][1] == SourceType.NEWS
    assert out[2][1] == SourceType.REVIEW


def test_dedupes_identical_queries():
    llm = _llm_returning([
        {"query": "same query", "source_type": "news"},
        {"query": "SAME query", "source_type": "news"},  # case-insensitive dupe
        {"query": "different",  "source_type": "review"},
    ])
    out = query_generator.generate_queries(
        target="Acme", industry="anything", llm=llm,
    )
    assert len(out) == 2


def test_caps_at_max_queries():
    big = [{"query": f"q{i}", "source_type": "news"} for i in range(20)]
    out = query_generator.generate_queries(
        target="Acme", industry="anything",
        llm=_llm_returning(big), max_queries=5,
    )
    assert len(out) == 5


def test_drops_overlong_queries():
    llm = _llm_returning([
        {"query": "ok query", "source_type": "news"},
        {"query": "x" * 220, "source_type": "news"},  # too long
    ])
    out = query_generator.generate_queries(
        target="Acme", industry="any", llm=llm,
    )
    assert len(out) == 1
    assert out[0][0] == "ok query"


def test_unknown_source_type_falls_back_to_other():
    llm = _llm_returning([
        {"query": "q", "source_type": "invented_label"},
    ])
    out = query_generator.generate_queries(
        target="Acme", industry="any", llm=llm,
    )
    assert out[0][1] == SourceType.OTHER


def test_returns_empty_on_malformed_json():
    def llm(_p): return "not valid json"
    assert query_generator.generate_queries(
        target="Acme", industry="any", llm=llm,
    ) == []


def test_returns_empty_on_llm_exception():
    def llm(_p): raise RuntimeError("vertex 500")
    assert query_generator.generate_queries(
        target="Acme", industry="any", llm=llm,
    ) == []


def test_tolerates_bare_list_response():
    """LLM returns a bare list instead of {queries:[...]} → still parsed."""
    def llm(_p):
        return json.dumps([{"query": "bare-list query", "source_type": "news"}])
    out = query_generator.generate_queries(
        target="Acme", industry="any", llm=llm,
    )
    assert len(out) == 1


def test_cached_variant_hits_cache_on_repeat():
    query_generator.clear_cache()
    calls: list[int] = []
    def llm(_p):
        calls.append(1)
        return json.dumps({"queries": [{"query": "cached", "source_type": "news"}]})
    out1 = query_generator.generate_queries_cached(
        target="Acme", industry="EV charging", region="US", stage="growth", llm=llm,
    )
    out2 = query_generator.generate_queries_cached(
        target="Acme", industry="EV charging", region="US", stage="growth", llm=llm,
    )
    assert out1 == out2
    assert len(calls) == 1, "second call should hit cache, not LLM"


def test_cached_variant_misses_on_different_target():
    query_generator.clear_cache()
    calls: list[int] = []
    def llm(_p):
        calls.append(1)
        return json.dumps({"queries": [{"query": "x", "source_type": "news"}]})
    query_generator.generate_queries_cached(
        target="Acme", industry="EV charging", llm=llm,
    )
    query_generator.generate_queries_cached(
        target="OtherCo", industry="EV charging", llm=llm,
    )
    assert len(calls) == 2, "different target should miss cache"
