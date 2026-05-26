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
