"""Check di idoneità trascrizione↔modello (modulo puro, niente I/O diretto).

Il timeout reale del 2026-06-17 (ECO 5.0, qwen2.5:7b, 2h11m) è il *sintomo*; la causa a monte
è "trascrizione troppo grande per il contesto del modello scelto". Questo modulo confronta i
token stimati della trascrizione col budget reale del provider e classifica l'idoneità, così
l'avviso è VISIBILE e DECIDIBILE PRIMA di spendere ore (passa a Claude, dividi, cambia modello).

Fonte UNICA delle costanti di stima token/chunk: l'analyzer ne fa alias (no duplicazione).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Literal

# Stima token: ~3 char/token (sovrastima per l'italiano → prudente). Coerente con
# ollama_provider._CHARS_PER_TOKEN; l'analyzer importa queste costanti da qui (fonte unica).
CHARS_PER_TOKEN = 3
PROMPT_OVERHEAD_TOKENS = 1500  # system + focus/guidance/shape/few-shot, senza la trascrizione
SUMMARY_CHUNK_WORDS = 2000  # dimensione di un chunk nel fallback chunk-summarize dell'analyzer
SUMMARY_TOKENS_PER_CHUNK = 400  # stima conservativa del riassunto di un singolo chunk
_AVG_CHARS_PER_WORD = 6  # media italiano incl. spazio (per la stima da durata audio)
_UNBOUNDED = 10_000_000  # budget "infinito" se il provider non espone i limiti (es. fake nei test)

FitLevel = Literal["ideal", "summarize", "over_even_summarized"]

_REC_SUMMARIZE = (
    "Per la massima fedeltà usa Claude (200k token di contesto) o un modello Ollama con più "
    "contesto, oppure dividi la registrazione in parti più brevi."
)
_REC_OVER = (
    "Dividi la registrazione in parti più brevi o usa Claude (200k token): anche riassunta, "
    "questa trascrizione supererebbe il contesto del modello."
)


@dataclass
class FitReport:
    tokens_est: int
    ctx_max: int
    budget: int
    level: FitLevel
    n_chunks: int
    ctx_is_fallback: bool
    reason: str
    recommendation: str


def _provider_limits(provider) -> tuple[int, int, bool]:
    """(budget_input_tokens, ctx_max_tokens, ctx_is_fallback) dal provider, con default ampi se
    il provider non espone i metodi (→ nessun riassunto, come il vecchio _needs_summary)."""
    budget_fn = getattr(provider, "context_budget_tokens", None)
    budget = budget_fn() if callable(budget_fn) else _UNBOUNDED
    max_fn = getattr(provider, "model_max_ctx", None)
    if callable(max_fn):
        ctx_max = max_fn()  # su OllamaProvider aggiorna anche _ctx_is_fallback (effetto)
    elif budget < _UNBOUNDED:
        ctx_max = budget + 2048  # Claude/altri senza model_max_ctx: stima dal budget
    else:
        ctx_max = _UNBOUNDED
    is_fallback = bool(getattr(provider, "_ctx_is_fallback", False))
    return budget, ctx_max, is_fallback


def _classify(tokens_est: int, words: int, budget: int, ctx_max: int, ctx_is_fallback: bool) -> FitReport:
    fb = " (contesto del modello non leggibile ora: stima prudente)" if ctx_is_fallback else ""
    if tokens_est <= budget:
        return FitReport(
            tokens_est=tokens_est,
            ctx_max=ctx_max,
            budget=budget,
            level="ideal",
            n_chunks=0,
            ctx_is_fallback=ctx_is_fallback,
            reason="La trascrizione entra nel contesto del modello: analisi in una passata, fedeltà massima." + fb,
            recommendation="",
        )
    n_chunks = max(1, ceil(words / SUMMARY_CHUNK_WORDS))
    summarized_est = n_chunks * SUMMARY_TOKENS_PER_CHUNK + PROMPT_OVERHEAD_TOKENS
    if summarized_est <= budget:
        return FitReport(
            tokens_est=tokens_est,
            ctx_max=ctx_max,
            budget=budget,
            level="summarize",
            n_chunks=n_chunks,
            ctx_is_fallback=ctx_is_fallback,
            reason=(
                f"La trascrizione (~{tokens_est} token) supera il budget del modello (~{budget} token): "
                f"verrà riassunta in {n_chunks} parti prima dell'analisi, con possibile perdita di dettaglio." + fb
            ),
            recommendation=_REC_SUMMARIZE,
        )
    return FitReport(
        tokens_est=tokens_est,
        ctx_max=ctx_max,
        budget=budget,
        level="over_even_summarized",
        n_chunks=n_chunks,
        ctx_is_fallback=ctx_is_fallback,
        reason=(
            f"La trascrizione (~{tokens_est} token) supera di molto il budget del modello (~{budget} token): "
            f"neanche un riassunto in {n_chunks} parti rientrerebbe." + fb
        ),
        recommendation=_REC_OVER,
    )


def assess_fit(transcript: str, provider) -> FitReport:
    """Idoneità ESATTA dalla trascrizione reale (post-trascrizione)."""
    budget, ctx_max, is_fallback = _provider_limits(provider)
    tokens_est = len(transcript) // CHARS_PER_TOKEN + PROMPT_OVERHEAD_TOKENS
    return _classify(tokens_est, len(transcript.split()), budget, ctx_max, is_fallback)


def estimate_from_duration(duration_s: float, provider, *, words_per_min: int = 140) -> FitReport:
    """Idoneità STIMATA dalla sola durata audio (preflight, prima di trascrivere) — per avvisare
    subito quando una registrazione lunga finirà riassunta/oltre il contesto del modello scelto."""
    budget, ctx_max, is_fallback = _provider_limits(provider)
    words = max(0, int(duration_s / 60 * words_per_min))
    tokens_est = (words * _AVG_CHARS_PER_WORD) // CHARS_PER_TOKEN + PROMPT_OVERHEAD_TOKENS
    return _classify(tokens_est, words, budget, ctx_max, is_fallback)
