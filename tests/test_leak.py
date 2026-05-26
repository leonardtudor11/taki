from guardrails.leak import filter_bundle, scan
from fixtures.sample import sample_bundle


def test_scan_flags_confidential():
    assert "confidential" in scan("CONFIDENTIAL — internal board deck")
    assert scan("Public pricing page, $79/seat") == []


def test_filter_withholds_confidential_source():
    b = sample_bundle()
    assert len(b.sources) == 5
    clean, flags = filter_bundle(b)
    # the contact source carries the CONFIDENTIAL marker -> withheld
    assert len(clean.sources) == 4
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
    assert len(again.sources) == 4
