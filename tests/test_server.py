"""Smoke tests for the local Flask backend (server.py).

These hit the in-process Werkzeug test client so they're fast and don't need
a real port. The SSE generator returns text/event-stream chunks; we just
assert the contract (status codes + the first events on a demo run).
"""

import json
import time

import pytest

import server


@pytest.fixture
def client():
    app = server.app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_status_endpoint_reports_modes(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["running"] is False
    assert data["modes"]["demo"] is True


def test_parse_urls_roundtrip():
    out = server._parse_urls([
        "https://x.com/pricing:pricing",
        "https://x.com/jobs:jobs",
        "https://x.com/about",
        "  ",
        "",
    ])
    # known suffixes are parsed; unknown defaults to SITE
    from agents.schemas import SourceType
    assert out[0] == ("https://x.com/pricing", SourceType.PRICING)
    assert out[1] == ("https://x.com/jobs", SourceType.JOBS)
    assert out[2] == ("https://x.com/about", SourceType.SITE)
    assert len(out) == 3


def test_run_demo_streams_full_cascade(client, tmp_path, monkeypatch):
    # redirect cache + brief writes into the tmp dir so the test doesn't
    # pollute the real frontend/brief.json
    from services import cache
    monkeypatch.setattr(cache, "DATA_DIR", tmp_path)
    monkeypatch.setattr(server, "FRONTEND_BRIEF", tmp_path / "brief.json")

    r = client.post("/api/run", json={"mode": "demo"})
    assert r.status_code == 200
    assert r.mimetype == "text/event-stream"
    # Werkzeug's test client buffers the streamed response; pull all data.
    body = r.get_data(as_text=True)
    events = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    phases = [e.get("phase") for e in events]
    # required milestones for a demo cascade
    for required in ("fetch", "pii", "leak", "dept", "grounding", "handoff", "assemble", "complete"):
        assert required in phases, f"missing phase: {required}"

    # final event signals success + brief target
    final = events[-1]
    assert final["phase"] == "complete"
    assert final["target"] == "Northwind Analytics"


def test_run_rejects_unknown_mode(client):
    r = client.post("/api/run", json={"mode": "rogue"})
    assert r.status_code == 400
    assert "unknown mode" in r.get_json()["error"]


def test_run_live_requires_target(client, monkeypatch):
    # force live-mode reachable so we hit the target check, not blockers
    monkeypatch.setattr(server, "_live_blockers", lambda: [])
    r = client.post("/api/run", json={"mode": "live"})
    assert r.status_code == 400
    assert "target required" in r.get_json()["error"]
