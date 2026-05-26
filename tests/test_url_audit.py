"""V7.6/V7.7 — URL audit + post-scrape quality gate."""

import pytest

from agents.schemas import SourceType
from services import url_audit
from services.url_audit import (
    AuditEntry,
    audit_url,
    audit_urls,
    is_low_quality,
    normalize_url,
)


# ─── normalize_url ────────────────────────────────────────────────────────

class TestNormalize:
    def test_already_clean_url_unchanged(self):
        assert normalize_url("https://stripe.com/pricing") == "https://stripe.com/pricing"

    def test_strips_whitespace(self):
        assert normalize_url("  https://stripe.com/pricing  ") == "https://stripe.com/pricing"

    def test_strips_trailing_punctuation(self):
        for trailing in (",", ".", ";", "):", "',", "\""):
            assert normalize_url(f"https://stripe.com{trailing}") == "https://stripe.com"

    def test_prepends_https_when_scheme_missing(self):
        assert normalize_url("stripe.com/pricing") == "https://stripe.com/pricing"
        assert normalize_url("www.stripe.com") == "https://www.stripe.com"

    def test_lowercases_hostname_keeps_path_case(self):
        assert normalize_url("https://Example.COM/MyPage") == "https://example.com/MyPage"

    def test_rejects_garbage(self):
        assert normalize_url("") is None
        assert normalize_url("   ") is None
        assert normalize_url(None) is None
        assert normalize_url(",.;") is None

    def test_rejects_non_http_schemes(self):
        assert normalize_url("ftp://example.com") is None
        assert normalize_url("javascript:alert(1)") is None
        assert normalize_url("file:///etc/passwd") is None

    def test_preserves_port_and_query(self):
        assert normalize_url("https://example.com:8080/p?q=1") == "https://example.com:8080/p?q=1"


# ─── dns_resolves ─────────────────────────────────────────────────────────

class TestDns:
    def test_returns_true_when_lookup_succeeds(self, monkeypatch):
        import socket
        monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [("info",)])
        assert url_audit.dns_resolves("https://example.com") is True

    def test_returns_false_on_nxdomain(self, monkeypatch):
        import socket

        def _raise(*a, **k):
            raise socket.gaierror("NXDOMAIN")
        monkeypatch.setattr(socket, "getaddrinfo", _raise)
        assert url_audit.dns_resolves("https://mulhlan.invalid") is False

    def test_returns_false_on_timeout(self, monkeypatch):
        import socket, time

        def _slow(*a, **k):
            time.sleep(5)  # longer than the audit timeout
            return [("info",)]
        monkeypatch.setattr(socket, "getaddrinfo", _slow)
        assert url_audit.dns_resolves("https://example.com", timeout=0.5) is False

    def test_returns_false_for_unparseable(self):
        assert url_audit.dns_resolves("not a url") is False


# ─── audit_url + audit_urls ───────────────────────────────────────────────

class TestAuditUrl:
    def test_ok_when_no_changes_and_dns_resolves(self, monkeypatch):
        monkeypatch.setattr(url_audit, "dns_resolves", lambda *a, **k: True)
        e = audit_url("https://stripe.com/pricing")
        assert e.status == "ok"
        assert e.normalized == "https://stripe.com/pricing"
        assert e.reason == ""

    def test_fixed_when_normalize_changed_the_url(self, monkeypatch):
        monkeypatch.setattr(url_audit, "dns_resolves", lambda *a, **k: True)
        e = audit_url("stripe.com/pricing")
        assert e.status == "fixed"
        assert e.normalized == "https://stripe.com/pricing"

    def test_dropped_when_unparseable(self):
        e = audit_url("???")
        # '???' becomes 'https://???' which has no valid hostname → dropped
        assert e.status == "dropped"
        assert "unparseable" in e.reason or "DNS" in e.reason

    def test_dropped_when_dns_fails(self, monkeypatch):
        monkeypatch.setattr(url_audit, "dns_resolves", lambda *a, **k: False)
        e = audit_url("https://mulhlan-typo.invalid")
        assert e.status == "dropped"
        assert "DNS" in e.reason

    def test_skip_dns_when_disabled(self, monkeypatch):
        # if dns=False even a non-resolving host should pass (offline test path)
        e = audit_url("https://offline-host.invalid", dns=False)
        assert e.status == "ok"


class TestAuditUrls:
    def test_keeps_only_passing_urls(self, monkeypatch):
        def fake_dns(url, timeout=3.0):
            return "bad" not in url
        monkeypatch.setattr(url_audit, "dns_resolves", fake_dns)
        urls = [
            ("https://good.com/x", SourceType.SITE),
            ("https://bad.com/y", SourceType.SITE),
            ("  https://needs-clean.com  ", SourceType.SITE),
        ]
        events = []
        kept, log = audit_urls(urls, on_event=events.append)
        # 2 of 3 kept; the bad one dropped; the clean one normalized to fixed
        assert len(kept) == 2
        assert kept[0][0] == "https://good.com/x"
        assert kept[1][0] == "https://needs-clean.com"
        statuses = [e.status for e in log]
        assert statuses == ["ok", "dropped", "fixed"]
        # event callback fired once per URL
        assert len(events) == 3
        assert events[1]["status"] == "dropped"
        assert events[1]["reason"]
        # source_type travels in the event payload
        assert all("source_type" in e for e in events)

    def test_empty_input_returns_empty(self):
        kept, log = audit_urls([])
        assert kept == []
        assert log == []


# ─── post-scrape quality gate ─────────────────────────────────────────────

class TestQualityGate:
    def test_passes_real_content(self):
        text = "About Acme — we make wind turbines. " * 50
        bad, reason = is_low_quality(text)
        assert bad is False
        assert reason == ""

    def test_rejects_too_short(self):
        bad, reason = is_low_quality("hi")
        assert bad is True
        assert "too short" in reason or "chars" in reason

    @pytest.mark.parametrize("snippet", [
        "Page Not Found — the requested page does not exist on this server. Please go back home." * 3,
        "Access Denied — you do not have permission to access this resource. Please contact admin." * 3,
        "Just a moment — checking your browser before accessing the site. Please enable cookies." * 3,
        "Sorry, you have been blocked. If you think this is an error, please contact our team." * 3,
    ])
    def test_rejects_error_pages(self, snippet):
        bad, reason = is_low_quality(snippet)
        assert bad is True
        assert reason

    def test_rejects_none(self):
        bad, reason = is_low_quality(None)
        assert bad is True
