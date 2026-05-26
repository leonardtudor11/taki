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
