"""Crea il provider LLM dalle impostazioni (claude default, ollama opzionale).
Unica fonte: usata da cli.py e app/pipeline.py (DRY)."""

from vokari import settings as settings_mod
from vokari.llm.anthropic_provider import AnthropicProvider
from vokari.llm.ollama_provider import OllamaProvider


def make_provider(s):
    if s.brain == "ollama":
        return OllamaProvider(endpoint=s.ollama_endpoint, model=s.ollama_model)
    return AnthropicProvider(api_key=settings_mod.get_api_key(), model=s.claude_model)


def make_consolidate_provider(s):
    """Provider per il solo CONSOLIDAMENTO (reduce del map-reduce, ADR-064/066), o None se
    non e' configurato nulla di diverso — nel qual caso l'analyzer riusa il provider normale.

    Vale solo per Ollama: con Claude il modello dell'analisi e' gia' abbastanza capace da
    consolidare, e una seconda configurazione sarebbe una scelta in piu' senza guadagno."""
    model = (getattr(s, "consolidate_model", "") or "").strip()
    if not model or s.brain != "ollama" or model == s.ollama_model:
        return None
    return OllamaProvider(endpoint=s.ollama_endpoint, model=model)
