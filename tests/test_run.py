from agents.schemas import CascadeBrief, SourceType
import run
from services import cache
from fixtures.fake_llm import fake_finance_llm, fake_gtm_llm, fake_security_llm
from fixtures.sample import sample_bundle


def test_generate_and_cache_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DATA_DIR", tmp_path)
    frontend = tmp_path / "brief.json"
    brief = run.generate_and_cache(
        sample_bundle(),
        gtm_llm=fake_gtm_llm,
        finance_llm=fake_finance_llm,
        security_llm=fake_security_llm,
        frontend_path=frontend,
    )
    assert isinstance(brief, CascadeBrief)
    assert cache.load_brief("Northwind Analytics") is not None
    assert frontend.exists()


def test_url_parser():
    parsed = run._parse_urls(
        ["https://x.com/pricing:pricing", "https://x.com/about"]
    )
    assert parsed[0] == ("https://x.com/pricing", SourceType.PRICING)
    assert parsed[1] == ("https://x.com/about", SourceType.SITE)
