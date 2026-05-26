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


def filter_bundle(bundle: SharedBundle) -> tuple[SharedBundle, list[str]]:
    """Withhold any source item containing a confidentiality marker.

    Returns (clean_bundle, flags) where each flag names the withheld URL and the
    marker that triggered it.
    """
    kept: list[SourceItem] = []
    flags: list[str] = []
    for item in bundle.sources:
        markers = scan(item.text)
        if markers:
            flags.append(f"withheld {item.url} (matched: {', '.join(markers)})")
        else:
            kept.append(item)
    return bundle.model_copy(update={"sources": kept}), flags
