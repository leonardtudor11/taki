from agents.schemas import AccountBrief, CascadeBrief
from services import cache
from fixtures.sample import sample_bundle


def test_slugify():
    assert cache.slugify("Northwind Analytics") == "northwind-analytics"
    assert cache.slugify("Acme, Inc.") == "acme-inc"
    assert cache.slugify("") == "unknown"


def test_bundle_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DATA_DIR", tmp_path)
    b = sample_bundle()
    cache.save_bundle(b)
    loaded = cache.load_bundle(b.target)
    assert loaded is not None
    assert loaded.target == b.target
    assert len(loaded.sources) == len(b.sources)
    assert loaded.sources[0].text == b.sources[0].text


def test_brief_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DATA_DIR", tmp_path)
    brief = CascadeBrief(target="Northwind Analytics", account_brief=AccountBrief(target="Northwind Analytics"))
    cache.save_brief(brief)
    loaded = cache.load_brief("Northwind Analytics")
    assert loaded is not None
    assert loaded.account_brief is not None


def test_load_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DATA_DIR", tmp_path)
    assert cache.load_bundle("does not exist") is None
    assert cache.load_brief("does not exist") is None
