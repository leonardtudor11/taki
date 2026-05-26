from guardrails.pii import EMAIL_TAG, PHONE_TAG, redact, redact_bundle
from fixtures.sample import PII_EMAIL, PII_PHONE, sample_bundle


def test_redacts_email_and_phone():
    text = f"Contact {PII_EMAIL} or {PII_PHONE} today."
    clean, n = redact(text)
    assert n == 2
    assert PII_EMAIL not in clean
    assert "555-0137" not in clean
    assert EMAIL_TAG in clean
    assert PHONE_TAG in clean


def test_does_not_redact_prices_or_counts():
    text = "Pro plan rose from $49 to $79; hiring 12 AEs; $40M Series B; churn 14%."
    clean, n = redact(text)
    assert n == 0
    assert clean == text


def test_redact_bundle_counts_all():
    b = sample_bundle()
    clean_bundle, total = redact_bundle(b)
    assert total == 2  # one email + one phone, both in the contact source
    joined = " ".join(clean_bundle.texts())
    assert PII_EMAIL not in joined
    assert "555-0137" not in joined
    # non-PII content survives
    assert "Series B" in joined
