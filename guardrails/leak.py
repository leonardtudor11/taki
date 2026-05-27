"""Leak / scope guard — public-web only.

Taki must never surface content that looks non-public or confidential, even if a
scraper happened to pull it. Any source item carrying a confidentiality marker
is withheld from the departments and logged.
"""

from __future__ import annotations

import re

from agents.schemas import SharedBundle, SourceItem

_MARKERS = [
    "confidential",
    "do not distribute",
    "internal use only",
    "internal board deck",
    "proprietary and confidential",
    "not for distribution",
    "internal memo",
    "under nda",
]
# Word-boundary lookarounds so "confidential" matches but "nonconfidential"
# / "unconfidentialish" do not (avoids false positives on adjacent letters).
_PATTERN = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(m) for m in _MARKERS) + r")(?![A-Za-z])",
    re.IGNORECASE,
)


def scan(text: str) -> list[str]:
    """Return the distinct confidentiality markers found in text."""
    found = {m.group(0).lower() for m in _PATTERN.finditer(text)}
    return sorted(found)


# V7.26 — high-trust publishers can mention "confidential" in news copy
# without being confidential themselves (Bloomberg writing about a leaked
# memo isn't itself the leak). Skip leak-scan for these domains.
_TRUSTED_PUBLISHERS = (
    "ft.com", "bloomberg.com", "reuters.com", "wsj.com", "nytimes.com",
    "washingtonpost.com", "economist.com", "theguardian.com",
    "telegraph.co.uk", "bbc.co.uk", "bbc.com", "cnbc.com", "forbes.com",
    "businessinsider.com", "fortune.com", "axios.com",
    "techcrunch.com", "theinformation.com", "wired.com", "arstechnica.com",
)


def _is_trusted_publisher(url: str) -> bool:
    import urllib.parse
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(host == s or host.endswith("." + s) for s in _TRUSTED_PUBLISHERS)


def filter_bundle(bundle: SharedBundle) -> tuple[SharedBundle, list[str]]:
    """Withhold any source item containing a confidentiality marker.

    V7.26 exemption: trusted public publishers (FT/Bloomberg/Reuters/etc.)
    are skipped — they routinely *report on* confidentiality without
    being confidential themselves, so flagging them is always a false
    positive that costs real news-of-record signal.

    Returns (clean_bundle, flags) where each flag names the withheld URL and the
    marker that triggered it.
    """
    kept: list[SourceItem] = []
    flags: list[str] = []
    for item in bundle.sources:
        if _is_trusted_publisher(item.url):
            kept.append(item)
            continue
        markers = scan(item.text)
        if markers:
            flags.append(f"withheld {item.url} (matched: {', '.join(markers)})")
        else:
            kept.append(item)
    return bundle.model_copy(update={"sources": kept}), flags
