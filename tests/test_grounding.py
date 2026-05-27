from agents.schemas import Citation, Claim, SourceType
from guardrails.grounding import filter_claims, is_grounded
from fixtures.sample import sample_bundle


def _grounded_claim():
    return Claim(
        text="Northwind raised Pro to $79/seat.",
        citations=[
            Citation(
                url="https://northwind.example/pricing",
                snippet="raised its Pro plan from $49 to $79",
                source_type=SourceType.PRICING,
            )
        ],
    )


def _hallucinated_claim():
    return Claim(
        text="Northwind is being acquired by Globex next week.",
        citations=[
            Citation(
                url="https://made-up.example",
                snippet="acquired by Globex next week",
                source_type=SourceType.NEWS,
            )
        ],
    )


def _uncited_claim():
    return Claim(text="Northwind has 500 employees.")


def test_grounded_claim_passes():
    b = sample_bundle()
    assert is_grounded(_grounded_claim(), [t.lower() for t in b.texts()])


def test_filter_drops_hallucination_and_uncited():
    b = sample_bundle()
    kept, dropped = filter_claims(
        [_grounded_claim(), _hallucinated_claim(), _uncited_claim()], b
    )
    assert len(kept) == 1
    assert kept[0].text.startswith("Northwind raised Pro")
    assert len(dropped) == 2
    assert "Globex" in " ".join(dropped)


def test_whitespace_insensitive_match():
    b = sample_bundle()
    claim = Claim(
        text="hiring AEs",
        citations=[
            Citation(
                url="https://northwind.example/careers",
                snippet="hiring   12   enterprise account executives",
                source_type=SourceType.JOBS,
            )
        ],
    )
    kept, dropped = filter_claims([claim], b)
    assert len(kept) == 1


def test_too_short_snippet_rejected_even_if_substring():
    # short snippets are too easy to find in unrelated contexts -> reject.
    b = sample_bundle()
    claim = Claim(
        text="they hire.",
        citations=[
            Citation(
                url="https://northwind.example/careers",
                snippet="hiring",  # 6 chars, below MIN_SNIPPET_LEN
                source_type=SourceType.JOBS,
            )
        ],
    )
    kept, dropped = filter_claims([claim], b)
    assert len(kept) == 0
    assert dropped == ["they hire."]


# ─── V7.21 — citation-level pruning ──────────────────────────────────────

def test_prune_drops_hallucinated_sibling_citation():
    """A claim w/ 1 verified + 1 hallucinated citation should survive but
    the rendered claim must carry only the verified citation. Previously
    the bad sibling rode along on the good one's coattails."""
    b = sample_bundle()
    claim = Claim(
        text="Northwind raised Pro to $79 and was acquired.",
        citations=[
            Citation(
                url="https://northwind.example/pricing",
                snippet="raised its Pro plan from $49 to $79",  # verified
                source_type=SourceType.PRICING,
            ),
            Citation(
                url="https://made-up.example",
                snippet="acquired by Globex next week",  # hallucinated
                source_type=SourceType.NEWS,
            ),
        ],
    )
    kept, dropped = filter_claims([claim], b)
    assert len(kept) == 1
    assert len(kept[0].citations) == 1
    assert kept[0].citations[0].url == "https://northwind.example/pricing"
    assert not dropped


def test_prune_is_noop_when_all_cites_grounded():
    """If every citation is verified, the original claim instance is returned
    unchanged — no needless model_copy churn."""
    b = sample_bundle()
    claim = _grounded_claim()
    kept, _ = filter_claims([claim], b)
    assert len(kept) == 1
    # all original cites preserved
    assert len(kept[0].citations) == len(claim.citations)


def test_prune_keeps_claim_when_only_one_of_three_verified():
    """Claim survives with ≥1 grounded cite. Sibling junk gets stripped."""
    b = sample_bundle()
    claim = Claim(
        text="multi-cite claim",
        citations=[
            Citation(
                url="https://made-up.example/1",
                snippet="lorem ipsum dolor sit amet consectetur",
                source_type=SourceType.NEWS,
            ),
            Citation(
                url="https://northwind.example/pricing",
                snippet="raised its Pro plan from $49 to $79",  # the only good one
                source_type=SourceType.PRICING,
            ),
            Citation(
                url="https://made-up.example/2",
                snippet="another fabrication that doesn't appear anywhere",
                source_type=SourceType.NEWS,
            ),
        ],
    )
    kept, _ = filter_claims([claim], b)
    assert len(kept) == 1
    assert len(kept[0].citations) == 1
    assert "Pro plan" in kept[0].citations[0].snippet
