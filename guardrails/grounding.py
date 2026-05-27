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


def _cite_is_grounded(cite, haystacks: list[str]) -> bool:
    """One citation is grounded iff its snippet (whitespace-normalised) appears
    verbatim in some source's text. Very-short snippets (< MIN_SNIPPET_LEN
    after normalisation) never ground — too easy to false-positive on common
    bigrams like 'to the'."""
    snippet = _norm(cite.snippet)
    if len(snippet) < MIN_SNIPPET_LEN:
        return False
    return any(snippet in h for h in haystacks)


def is_grounded(claim: Claim, haystacks: list[str]) -> bool:
    """A claim is grounded iff ≥1 of its citations is grounded."""
    if not claim.citations:
        return False
    return any(_cite_is_grounded(c, haystacks) for c in claim.citations)


def prune_citations(claim: Claim, haystacks: list[str]) -> Claim:
    """V7.21 — return a new Claim whose citations include only the verified ones.

    The claim-level `is_grounded` predicate saves a claim if ≥1 citation
    snippet matches the bundle, but sibling unverified citations were
    previously kept and rendered as if they were evidence. This was a real
    hallucination vector: a true citation could carry a fabricated sibling
    along for the ride. After this pass, every rendered citation has been
    individually verified against the bundle.

    No-op (returns the original claim) when no citations were dropped.
    """
    if not claim.citations:
        return claim
    kept = [c for c in claim.citations if _cite_is_grounded(c, haystacks)]
    if len(kept) == len(claim.citations):
        return claim
    return claim.model_copy(update={"citations": kept})


def filter_claims(
    claims: list[Claim], bundle: SharedBundle
) -> tuple[list[Claim], list[str]]:
    """Return (grounded_claims, dropped_claim_texts).

    A claim survives if ≥1 citation snippet appears verbatim in the bundle.
    Survivors have their unverified citations pruned (V7.21) so the
    rendered brief carries only verified evidence per claim.
    """
    haystacks = [_norm(t) for t in bundle.texts()]
    kept: list[Claim] = []
    dropped: list[str] = []
    for claim in claims:
        if is_grounded(claim, haystacks):
            kept.append(prune_citations(claim, haystacks))
        else:
            dropped.append(claim.text)
    return kept, dropped
