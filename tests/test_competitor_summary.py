"""V7.38 — competitor mini-bundle tests.

Pins the contract for build_summaries: SERP→Unlock→LLM per competitor,
soft-fail individually, cap at MAX_COMPETITORS, never raise.
"""

from __future__ import annotations

import json

from agents import competitor_summary
from agents.schemas import BusinessProfile, CompetitorSummary


class _FakeClient:
    """Minimal BD client stub. SERP returns canned HTML; unlock returns
    canned body per URL. Records calls so tests can assert order."""

    serp_zone = "test"
    unlocker_zone = "test"

    def __init__(self, serp_html: dict[str, str], bodies: dict[str, str]):
        self.serp_html = serp_html
        self.bodies = bodies
        self.serp_calls: list[str] = []
        self.unlock_calls: list[str] = []

    def serp(self, query: str) -> str:
        self.serp_calls.append(query)
        return self.serp_html.get(query, "")

    def unlock(self, url: str) -> str:
        self.unlock_calls.append(url)
        if url not in self.bodies:
            raise RuntimeError(f"404 stub: {url}")
        return self.bodies[url]


def _real_body(stem: str, n: int = 120) -> str:
    return f"<html><body>{('real ' + stem + ' content ') * n}</body></html>"


def _good_llm_for(name: str):
    def _fn(_p):
        return json.dumps({
            "positioning":  f"{name} sells X to Y with Z.",
            "pricing_hint": "$99/seat/mo and up",
            "stage_hint":   "growth",
            "why_relevant": f"{name} competes with Acme on the mid-market segment.",
        })
    return _fn


def _serp_html(url: str) -> str:
    """SERP results HTML w/ a single result link the parse_serp_results regex will catch."""
    return f'<html><body><a href="{url}">result</a></body></html>'


def test_empty_competitor_list_returns_empty():
    client = _FakeClient({}, {})
    out = competitor_summary.build_summaries(
        target_name="Acme", target_profile=None, competitor_names=[],
        client=client,  # type: ignore[arg-type]
    )
    assert out == []


def test_full_path_builds_one_summary_per_competitor():
    """SERP finds URL, scrape succeeds, LLM emits all 4 fields → entry shipped."""
    rival_url = "https://rival.co/"
    client = _FakeClient(
        serp_html={"Rival official site": _serp_html(rival_url)},
        bodies={rival_url: _real_body("rival home")},
    )
    out = competitor_summary.build_summaries(
        target_name="Acme",
        target_profile=BusinessProfile(name="Acme", url="https://acme.co", industry="SaaS"),
        competitor_names=["Rival"],
        client=client,  # type: ignore[arg-type]
        llm=_good_llm_for("Rival"),
    )
    assert len(out) == 1
    assert isinstance(out[0], CompetitorSummary)
    assert out[0].name == "Rival"
    assert out[0].url == rival_url
    assert out[0].pricing_hint.startswith("$99")
    assert "Acme" in out[0].why_relevant


def test_caps_at_max_competitors():
    client = _FakeClient(serp_html={}, bodies={})
    # Even if 10 names passed, only MAX_COMPETITORS are attempted.
    out = competitor_summary.build_summaries(
        target_name="Acme", target_profile=None,
        competitor_names=[f"Rival{i}" for i in range(10)],
        client=client,  # type: ignore[arg-type]
        llm=_good_llm_for("Rival"),
    )
    assert len(out) == 0  # all SERP-lookup-fail; no summaries
    assert len(client.serp_calls) == competitor_summary.MAX_COMPETITORS


def test_serp_failure_skips_competitor_silently():
    """SERP returns empty HTML → no URL found → entry skipped."""
    client = _FakeClient(serp_html={"X official site": ""}, bodies={})
    events: list[dict] = []
    out = competitor_summary.build_summaries(
        target_name="Acme", target_profile=None,
        competitor_names=["X"], client=client,  # type: ignore[arg-type]
        llm=_good_llm_for("X"), on_event=events.append,
    )
    assert out == []
    assert any(e["status"] == "lookup_failed" and e["name"] == "X" for e in events)


def test_scrape_failure_skips_competitor():
    """SERP gives URL; unlock raises → entry skipped."""
    bad_url = "https://blocked.co/"
    client = _FakeClient(
        serp_html={"Blocked official site": _serp_html(bad_url)},
        bodies={},  # unlock will raise — URL not in bodies
    )
    out = competitor_summary.build_summaries(
        target_name="Acme", target_profile=None,
        competitor_names=["Blocked"], client=client,  # type: ignore[arg-type]
        llm=_good_llm_for("Blocked"),
    )
    assert out == []


def test_llm_returns_empty_dict_skips_entry():
    """LLM returns {} → required-field check fails → entry skipped."""
    url = "https://ok.co/"
    client = _FakeClient(
        serp_html={"OK official site": _serp_html(url)},
        bodies={url: _real_body("ok home")},
    )
    out = competitor_summary.build_summaries(
        target_name="Acme", target_profile=None,
        competitor_names=["OK"], client=client,  # type: ignore[arg-type]
        llm=lambda _p: "{}",
    )
    assert out == []


def test_llm_missing_one_required_field_skips_entry():
    url = "https://ok.co/"
    client = _FakeClient(
        serp_html={"OK official site": _serp_html(url)},
        bodies={url: _real_body("ok home")},
    )
    # Missing pricing_hint → required-field check should fail.
    def llm(_p):
        return json.dumps({
            "positioning":  "X",
            "stage_hint":   "growth",
            "why_relevant": "Y",
        })
    out = competitor_summary.build_summaries(
        target_name="Acme", target_profile=None,
        competitor_names=["OK"], client=client,  # type: ignore[arg-type]
        llm=llm,
    )
    assert out == []


def test_dedupes_duplicate_serp_urls():
    """Two competitor names resolve to the same primary URL → second skipped."""
    same_url = "https://shared.co/"
    client = _FakeClient(
        serp_html={
            "First official site":  _serp_html(same_url),
            "Second official site": _serp_html(same_url),
        },
        bodies={same_url: _real_body("shared home")},
    )
    out = competitor_summary.build_summaries(
        target_name="Acme", target_profile=None,
        competitor_names=["First", "Second"],
        client=client,  # type: ignore[arg-type]
        llm=_good_llm_for("X"),
    )
    assert len(out) == 1
    assert out[0].name == "First"


def test_llm_exception_caught_per_competitor():
    """LLM raises → entry skipped; other competitors still processed."""
    u1 = "https://a.co/"
    u2 = "https://b.co/"
    client = _FakeClient(
        serp_html={
            "A official site": _serp_html(u1),
            "B official site": _serp_html(u2),
        },
        bodies={u1: _real_body("a"), u2: _real_body("b")},
    )
    state = {"calls": 0}
    def llm(_p):
        state["calls"] += 1
        if state["calls"] == 1:
            raise RuntimeError("vertex timeout")
        return json.dumps({
            "positioning":  "B sells things.",
            "pricing_hint": "unstated",
            "stage_hint":   "growth",
            "why_relevant": "B competes with Acme on positioning.",
        })
    out = competitor_summary.build_summaries(
        target_name="Acme", target_profile=None,
        competitor_names=["A", "B"], client=client,  # type: ignore[arg-type]
        llm=llm,
    )
    assert len(out) == 1
    assert out[0].name == "B"
