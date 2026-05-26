from guardrails.leak import filter_bundle, scan
from fixtures.sample import sample_bundle


def test_scan_flags_confidential():
    assert "confidential" in scan("CONFIDENTIAL — internal board deck")
    assert scan("Public pricing page, $79/seat") == []


def test_filter_withholds_confidential_source():
    b = sample_bundle()
    # V6 fixture has 8 sources; the contact source carries the CONFIDENTIAL
    # marker so the leak guard withholds exactly one -> 7 remain.
    assert len(b.sources) == 8
    clean, flags = filter_bundle(b)
    assert len(clean.sources) == 7
    assert len(flags) == 1
    assert "contact" in flags[0]
    # public sources survive
    urls = [s.url for s in clean.sources]
    assert "https://northwind.example/pricing" in urls


def test_clean_bundle_has_no_flags():
    b = sample_bundle()
    clean, _ = filter_bundle(b)
    again, flags = filter_bundle(clean)
    assert flags == []
    assert len(again.sources) == 7


def test_word_boundary_no_false_positive_inside_longer_word():
    # "confidential" inside a longer word should NOT trigger
    assert scan("Discussed nonconfidentialish matters openly.") == []
    assert scan("confidentialish") == []
    # whole-word still triggers
    assert "confidential" in scan("This is confidential.")
