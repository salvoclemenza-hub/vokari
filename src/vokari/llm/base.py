"""Interfaccia provider LLM (sincrona). Implementata da Anthropic e Ollama."""

import json
import re
from typing import Protocol


class LLMError(RuntimeError):
    """Errore d'uso del provider (chiave mancante, risposta non-JSON, rete)."""


class LLMProvider(Protocol):
    def chat_json(self, system: str, user: str, *, json_schema: dict | None = None) -> dict: ...
    def chat_text(self, system: str, user: str) -> str: ...

    # Variante streaming OPZIONALE di chat_json: ritorna lo stesso dict, ma chiama
    # `on_delta(testo_grezzo_accumulato)` a ogni chunk (per l'anteprima live dell'analisi) e
    # onora `should_cancel()` interrompendo la generazione. I provider che non la implementano
    # restano validi: il chiamante (analyzer) fa fallback a chat_json via hasattr.
    def chat_json_stream(
        self,
        system: str,
        user: str,
        *,
        json_schema: dict | None = None,
        on_delta=None,
        should_cancel=None,
    ) -> dict: ...


def parse_json_lenient(text: str) -> dict:
    """Estrae un dict JSON da `text`, tollerando code-fence e testo introduttivo.

    Gestisce: ```json\\n...\\n```, ```\\n...\\n```, testo prima della fence, JSON nudo.
    """
    t = text.strip()
    # Cerca una fence ovunque nel testo (gestisce testo introduttivo prima della fence)
    fence_match = re.search(r"```[a-zA-Z]*\s*\n(.*?)(?:\n```|$)", t, re.DOTALL)
    if fence_match:
        t = fence_match.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError as e:
        raise LLMError(f"Risposta LLM non è JSON valido: {e}") from e
