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


def test_consolidate_provider_only_when_it_adds_something():
    """None quando non c'e' nulla da guadagnare: nessun modello scelto, stesso modello
    dell'analisi, o cervello Claude (li' il modello principale consolida gia' bene)."""
    from vokari.llm.factory import make_consolidate_provider
    from vokari.settings import Settings

    base = Settings(brain="ollama", ollama_model="qwen2.5:7b")
    assert make_consolidate_provider(base) is None
    assert make_consolidate_provider(Settings(brain="ollama", ollama_model="q", consolidate_model="q")) is None
    assert make_consolidate_provider(Settings(brain="claude", consolidate_model="granite4.2:8b")) is None

    prov = make_consolidate_provider(
        Settings(brain="ollama", ollama_model="qwen2.5:7b", consolidate_model="granite4.2:8b")
    )
    assert prov is not None and prov.model == "granite4.2:8b"
