"""Crea il provider LLM dalle impostazioni (claude default, ollama opzionale).
Unica fonte: usata da cli.py e app/pipeline.py (DRY)."""

from vokari import settings as settings_mod
from vokari.llm.anthropic_provider import AnthropicProvider
from vokari.llm.ollama_provider import OllamaProvider


def make_provider(s):
    if s.brain == "ollama":
        return OllamaProvider(endpoint=s.ollama_endpoint, model=s.ollama_model)
    return AnthropicProvider(api_key=settings_mod.get_api_key(), model=s.claude_model)
