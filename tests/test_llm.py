import pytest

from services import llm


def test_default_raises_with_no_config(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        llm.get_default_llm()


def test_default_picks_studio_when_only_api_key(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    fn = llm.get_default_llm()
    assert callable(fn)


def test_vertex_requires_project(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    with pytest.raises(RuntimeError):
        llm.get_vertex_llm()


def test_studio_requires_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        llm.get_studio_llm()
