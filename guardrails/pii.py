"""PII redaction guard.

Strips personal data from scraped text before it reaches the LLM or the final
brief. Conservative by design: emails and phone numbers (>=10 digits) only, to
avoid clobbering legitimate figures like prices or headcounts.
"""

from __future__ import annotations

import re

from agents.schemas import SharedBundle, SourceItem

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# candidate phone run: optional +, then digits/spaces/()-. ending in a digit
_PHONE_CANDIDATE = re.compile(r"\+?\d[\d\s().\-]{7,}\d")

EMAIL_TAG = "[REDACTED-EMAIL]"
PHONE_TAG = "[REDACTED-PHONE]"


def redact(text: str) -> tuple[str, int]:
    """Return (clean_text, redaction_count)."""
    count = 0

    def _email_sub(_m: re.Match) -> str:
        nonlocal count
        count += 1
        return EMAIL_TAG

    text = _EMAIL.sub(_email_sub, text)

    def _phone_sub(m: re.Match) -> str:
        nonlocal count
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) >= 10:
            count += 1
            return PHONE_TAG
        return m.group(0)

    text = _PHONE_CANDIDATE.sub(_phone_sub, text)
    return text, count


def redact_bundle(bundle: SharedBundle) -> tuple[SharedBundle, int]:
    """Return a redacted copy of the bundle and the total redaction count."""
    total = 0
    new_sources: list[SourceItem] = []
    for item in bundle.sources:
        clean, n = redact(item.text)
        total += n
        new_sources.append(item.model_copy(update={"text": clean}))
    return bundle.model_copy(update={"sources": new_sources}), total
