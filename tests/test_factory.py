from vokari.llm.factory import make_provider
from vokari.llm.ollama_provider import OllamaProvider
from vokari.settings import Settings


def test_make_provider_ollama():
    s = Settings(brain="ollama", ollama_endpoint="http://x:1", ollama_model="gemma2:9b")
    assert isinstance(make_provider(s), OllamaProvider)


def test_make_provider_claude(monkeypatch):
    import vokari.llm.factory as F

    monkeypatch.setattr(F.settings_mod, "get_api_key", lambda: "sk-ant-test")
    s = Settings(brain="claude", claude_model="claude-opus-4-8")
    assert make_provider(s).model == "claude-opus-4-8"
