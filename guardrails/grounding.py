"""Grounding guard — kill hallucinations.

A claim survives only if at least one of its citations quotes a snippet that
actually appears in the SharedBundle the departments read. Uncited or
unmatched claims are dropped and logged. This is the only "adversarial"
mechanic in Taki, and it is purely defensive.
"""

from __future__ import annotations

import re

from agents.schemas import Claim, SharedBundle


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


# Substring matching can be tricked with a tiny snippet that appears in many
# unrelated contexts ("is", "to", "the"). Require a meaningful minimum length
# so the snippet must carry enough phrase context to be a real citation.
MIN_SNIPPET_LEN = 15


def is_grounded(claim: Claim, haystacks: list[str]) -> bool:
    if not claim.citations:
        return False
    for cite in claim.citations:
        snippet = _norm(cite.snippet)
        if len(snippet) < MIN_SNIPPET_LEN:
            continue
        if any(snippet in h for h in haystacks):
            return True
    return False


def filter_claims(
    claims: list[Claim], bundle: SharedBundle
) -> tuple[list[Claim], list[str]]:
    """Return (grounded_claims, dropped_claim_texts)."""
    haystacks = [_norm(t) for t in bundle.texts()]
    kept: list[Claim] = []
    dropped: list[str] = []
    for claim in claims:
        if is_grounded(claim, haystacks):
            kept.append(claim)
        else:
            dropped.append(claim.text)
    return kept, dropped
