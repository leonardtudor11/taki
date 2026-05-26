"""URL audit — pre-scrape normalization + DNS resolution check.

Catches the common ways a user-pasted URL ends up un-scrapeable BEFORE the
cascade wastes a Bright Data request on it (and before the user wastes
minutes waiting for a 30s × 3-retry timeout per bad URL).

Two layers:

  normalize_url(raw) — deterministic clean-up. NEVER changes the meaning of
    the URL, only the surface form:
      • strip leading/trailing whitespace
      • strip trailing punctuation (',.;:)')
      • prepend 'https://' when the user pasted a bare host
      • lowercase the hostname (paths stay case-sensitive)
    Returns None if the result still isn't a usable http(s) URL.

  dns_resolves(url, timeout=3) — fires socket.getaddrinfo in a worker thread
    so the audit step has a hard ceiling. NXDOMAIN / unresolvable hosts get
    dropped here for ~0 cost instead of after a 30s BD timeout.

  audit_urls((url, source_type) tuples) — runs both above per URL, emits
    audit events via the optional `on_event` callback, returns
    (clean_url_tuples_that_passed, audit_log_entries).

The audit is deliberately conservative: we never try to GUESS what a typo
'mulhlan.com' should have been — that's hallucination territory. Either
the URL resolves (we use it) or it doesn't (we drop it cleanly and tell
the user). The cascade keeps running on whatever passed.
"""

from __future__ import annotations

import concurrent.futures
import socket
import urllib.parse
from dataclasses import dataclass, asdict
from typing import Callable, Optional


# trailing junk we silently strip — users routinely paste with these because
# of how punctuation around a URL travels in chat / emails.
_TRAILING_JUNK = ",.;:)>\"'"

# scheme matcher — we treat anything before '://' as a scheme regardless of case.
_SCHEME_RE_HINT = "://"


@dataclass
class AuditEntry:
    """One per audited URL — what came in, what we used, why."""
    original: str
    normalized: Optional[str]
    status: str          # 'ok' | 'fixed' | 'dropped'
    reason: str = ""     # populated when status == 'dropped'


def normalize_url(raw: str) -> Optional[str]:
    """Best-effort cleanup of a user-pasted URL.

    Returns the cleaned URL string, or None if the input can't be coerced
    into a usable http(s) URL. Callers should check for None.
    """
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    # strip trailing punctuation (one round is enough for typical paste artifacts)
    while s and s[-1] in _TRAILING_JUNK:
        s = s[:-1]
    if not s:
        return None
    # prepend https:// if no scheme is present. Common when a user types
    # 'example.com/pricing' — without a scheme urlparse can't see the host.
    if _SCHEME_RE_HINT not in s:
        # but don't double-prefix if they typed 'www.example.com'; that case
        # also falls under 'no scheme'.
        s = "https://" + s
    try:
        parsed = urllib.parse.urlsplit(s)
    except (ValueError, TypeError):
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    # parsed.hostname / parsed.port can themselves raise ValueError on
    # malformed authorities (e.g. 'javascript:alert(1)' parsed with scheme
    # stripped — caught here so audit returns None cleanly).
    try:
        if not parsed.hostname:
            return None
        host = parsed.hostname.lower()
        port = f":{parsed.port}" if parsed.port else ""
    except (ValueError, TypeError):
        return None
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    netloc = f"{userinfo}{host}{port}"
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def dns_resolves(url: str, timeout: float = 3.0) -> bool:
    """Threaded DNS lookup with a hard deadline.

    socket.getaddrinfo respects the system resolver timeout (typically 5-15s
    on Linux/macOS). Running it inside a thread with a future.timeout keeps
    the audit step bounded so a slow / dead resolver can't freeze the
    cascade before it even starts.

    Treats AAAA-only hosts as resolvable (uses AF_UNSPEC).
    """
    try:
        host = urllib.parse.urlsplit(url).hostname
    except (ValueError, TypeError):
        return False
    if not host:
        return False

    def _lookup() -> bool:
        try:
            socket.getaddrinfo(host, None)
            return True
        except (socket.gaierror, socket.herror, OSError):
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_lookup)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            return False
        except Exception:
            return False


def audit_url(raw: str, *, dns: bool = True, dns_timeout: float = 3.0) -> AuditEntry:
    """Audit a single URL. Lower-level than audit_urls; useful in tests."""
    norm = normalize_url(raw)
    if norm is None:
        return AuditEntry(
            original=raw, normalized=None, status="dropped",
            reason="unparseable URL — neither host nor scheme could be inferred",
        )
    if dns and not dns_resolves(norm, timeout=dns_timeout):
        return AuditEntry(
            original=raw, normalized=norm, status="dropped",
            reason="DNS lookup failed — the hostname does not resolve (typo? domain expired?)",
        )
    status = "ok" if norm == raw else "fixed"
    return AuditEntry(original=raw, normalized=norm, status=status)


def audit_urls(
    urls: list[tuple[str, object]],
    *,
    dns: bool = True,
    dns_timeout: float = 3.0,
    on_event: Optional[Callable[[dict], None]] = None,
) -> tuple[list[tuple[str, object]], list[AuditEntry]]:
    """Audit a list of (url, source_type) tuples in order.

    Returns:
        - clean_urls: tuples that passed audit, with the URL normalized.
        - log: AuditEntry per input URL (in input order).

    The on_event callback (if supplied) fires once per URL with a dict
    payload — used by the server to stream audit events down the SSE
    channel so the dashboard can show 'fixing URL' / 'dropping URL' in
    real time.
    """
    clean: list[tuple[str, object]] = []
    log: list[AuditEntry] = []
    for url, source_type in urls or []:
        entry = audit_url(url, dns=dns, dns_timeout=dns_timeout)
        log.append(entry)
        if on_event is not None:
            try:
                payload = asdict(entry)
                payload["source_type"] = (
                    source_type.value if hasattr(source_type, "value") else str(source_type)
                )
                on_event(payload)
            except Exception:
                pass
        if entry.status != "dropped" and entry.normalized:
            clean.append((entry.normalized, source_type))
    return clean, log


# ─── post-scrape quality gate ────────────────────────────────────────────

# Below this length, the page text is almost certainly an error / challenge
# page rather than real content. Real public-facing sites have at minimum a
# nav + a hero block which lands well above 150 chars after tag-stripping.
MIN_TEXT_CHARS = 150


# Short blocks of text that strongly indicate the response wasn't real page
# content — bot challenges, error pages, geo-blocks, login walls. Matched
# case-insensitively against the first ~500 chars of the scraped text.
_ERROR_PATTERNS = (
    "page not found",
    "404 not found",
    "this page isn't working",
    "access denied",
    "403 forbidden",
    "you don't have permission",
    "just a moment",         # cloudflare challenge
    "checking your browser", # cloudflare challenge
    "enable javascript and cookies to continue",  # cf challenge variant
    "sorry, you have been blocked",
    "are you a robot",
    "please complete the security check",
    "captcha",
    "service unavailable",
    "503 service",
    "521 web server is down",
)


def is_low_quality(text: str) -> tuple[bool, str]:
    """Returns (rejected?, reason). Reason is empty when the text passes."""
    if not isinstance(text, str):
        return True, "no text"
    stripped = text.strip()
    if len(stripped) < MIN_TEXT_CHARS:
        return True, f"page too short — only {len(stripped)} chars (likely an error page)"
    head = stripped[:500].lower()
    for pat in _ERROR_PATTERNS:
        if pat in head:
            return True, f"page looks like a '{pat}' response (bot challenge or block)"
    return False, ""
