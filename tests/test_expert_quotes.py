"""V7.34 — Expert-quote extractor unit tests.

Pins the agent contract: dedupe by verbatim text, drop entries without
a quote, clamp overlong quotes, tolerate both {"quotes":[...]} and bare
[...] response shapes, fall back to [] on any LLM/parse failure.
"""

from __future__ import annotations

import json

from agents import expert_quotes
from agents.schemas import ExpertQuote, SharedBundle, SourceItem, SourceType
from fixtures.fake_llm import fake_expert_quotes_llm


def _bundle_with_text(text: str = "Some scraped body content " * 80) -> SharedBundle:
    return SharedBundle(
        target="Acme",
        sources=[SourceItem(
            source_type=SourceType.SITE,
            url="https://acme.example/",
            text=text,
        )],
    )


def test_analyze_returns_empty_on_empty_bundle():
    assert expert_quotes.analyze(SharedBundle(target="X")) == []


def test_analyze_returns_quotes_from_fake_llm():
    quotes = expert_quotes.analyze(_bundle_with_text(), llm=fake_expert_quotes_llm)
    assert len(quotes) == 3
    assert all(isinstance(q, ExpertQuote) for q in quotes)
    # External voices ranked first per the prompt rules.
    assert quotes[0].organization == "Gartner"
    assert quotes[1].organization == "Reuters"
    assert quotes[2].organization == "Northwind Analytics"
    # Verbatim text + citation threaded through.
    assert "$49 to $79" in quotes[1].quote
    assert quotes[0].citation.startswith("https://")


def test_analyze_dedupes_identical_quotes():
    """LLM accidentally repeats the same verbatim text → only one entry kept."""
    def llm(_p):
        return json.dumps({"quotes": [
            {"name": "A", "quote": "Same exact line of text."},
            {"name": "B", "quote": "Same exact line of text."},
            {"name": "C", "quote": "A different line."},
        ]})
    quotes = expert_quotes.analyze(_bundle_with_text(), llm=llm)
    assert len(quotes) == 2
    assert {q.quote for q in quotes} == {"Same exact line of text.", "A different line."}


def test_analyze_drops_entries_without_quote_text():
    def llm(_p):
        return json.dumps({"quotes": [
            {"name": "Has Quote", "quote": "Real verbatim text."},
            {"name": "No Quote", "role": "CEO", "organization": "Acme"},
            {"name": "Empty Quote", "quote": "   "},
        ]})
    quotes = expert_quotes.analyze(_bundle_with_text(), llm=llm)
    assert len(quotes) == 1
    assert quotes[0].name == "Has Quote"


def test_analyze_clamps_overlong_quotes():
    long_quote = "x" * 500
    def llm(_p):
        return json.dumps({"quotes": [{"name": "A", "quote": long_quote}]})
    quotes = expert_quotes.analyze(_bundle_with_text(), llm=llm)
    assert len(quotes) == 1
    assert len(quotes[0].quote) <= 320
    assert quotes[0].quote.endswith("...")


def test_analyze_tolerates_bare_list_response():
    """LLM returns a bare list instead of {quotes: [...]} → still parsed."""
    def llm(_p):
        return json.dumps([
            {"name": "Solo", "quote": "Bare-list verbatim."},
        ])
    quotes = expert_quotes.analyze(_bundle_with_text(), llm=llm)
    assert len(quotes) == 1
    assert quotes[0].quote == "Bare-list verbatim."


def test_analyze_returns_empty_on_malformed_json():
    def llm(_p):
        return "not valid json at all"
    assert expert_quotes.analyze(_bundle_with_text(), llm=llm) == []


def test_analyze_returns_empty_on_llm_exception():
    def llm(_p):
        raise RuntimeError("vertex timeout")
    assert expert_quotes.analyze(_bundle_with_text(), llm=llm) == []


def test_analyze_returns_empty_on_non_dict_entries():
    def llm(_p):
        return json.dumps({"quotes": [
            "not a dict",
            42,
            None,
            {"name": "Real", "quote": "Real quote."},
        ]})
    quotes = expert_quotes.analyze(_bundle_with_text(), llm=llm)
    assert len(quotes) == 1
    assert quotes[0].name == "Real"


def test_analyze_caps_at_max_quotes():
    big = {"quotes": [
        {"name": f"P{i}", "quote": f"Unique quote number {i}."}
        for i in range(50)
    ]}
    def llm(_p):
        return json.dumps(big)
    quotes = expert_quotes.analyze(_bundle_with_text(), llm=llm)
    assert len(quotes) == expert_quotes.MAX_QUOTES
