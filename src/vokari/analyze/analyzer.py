"""Transcript -> Analysis (un JSON). Fallback chunk-summarize solo per testi enormi.

Soglia generosa: la trascrizione intera va in un'unica chiamata (spec §7); il
chunk-and-merge annacqua le decisioni, quindi è solo un paracadute oltre ~100k token.
"""

from vokari.analyze import fit, prompts
from vokari.analyze.schema import Analysis
from vokari.llm.base import LLMError

FALLBACK_WORD_THRESHOLD = 70000  # paracadute assoluto (proxy parole) per provider senza budget
# Fonte unica delle costanti di chunk in fit.py; alias a livello modulo perché i test
# monkeypatchano `analyzer.SUMMARY_CHUNK_WORDS` e `_summarize_long` legge il globale del modulo.
SUMMARY_CHUNK_WORDS = fit.SUMMARY_CHUNK_WORDS

_SYS_SUMMARY = (
    "Riassumi in italiano questa porzione di trascrizione mantenendo "
    "decisioni, nomi, numeri e prossimi passi. Sii conciso."
)


def _needs_summary(transcript: str, provider) -> bool:
    """True se la trascrizione va riassunta PRIMA dell'analisi per non sforare il contesto.

    Soglia ASSOLUTA a parole (paracadute storico, per provider senza budget noto) + delega al
    check di idoneità (fit.assess_fit), che confronta i token stimati col budget reale del
    modello (Ollama: max da /api/show; Claude: ~200k). Così una trascrizione troppo lunga viene
    riassunta a tratti (con warning) invece di far troncare il prompt in silenzio — il bug delle
    liste vuote. DRY: la stessa logica alimenta l'evento analysis_fit (Check A)."""
    if len(transcript.split()) > FALLBACK_WORD_THRESHOLD:
        return True
    return fit.assess_fit(transcript, provider).level != "ideal"


def _summarize_long(transcript: str, provider, *, emit=None, should_cancel=None) -> str:
    words = transcript.split()
    chunks = [" ".join(words[i : i + SUMMARY_CHUNK_WORDS]) for i in range(0, len(words), SUMMARY_CHUNK_WORDS)]
    # Trascrizione enorme (~8h): N chiamate LLM in serie. Avvisa (riusa l'evento `warning`,
    # niente nuovo evento → no drift di contratto) e onora la cancellazione tra un chunk e
    # l'altro: senza, l'utente resterebbe minuti senza feedback né modo di fermare.
    if emit:
        emit(
            "warning",
            {
                "messages": [
                    f"Trascrizione oltre il contesto del modello: la riassumo in {len(chunks)} parti "
                    "prima dell'analisi (qualche minuto; il dettaglio può ridursi). Per la massima "
                    "fedeltà usa un modello con contesto più ampio o dividi la registrazione."
                ]
            },
        )
    summaries: list[str] = []
    for i, c in enumerate(chunks):
        if should_cancel and should_cancel():
            break
        summaries.append(provider.chat_text(_SYS_SUMMARY, f"Porzione {i + 1}/{len(chunks)}:\n\n{c}"))
    return "\n\n---\n\n".join(summaries)


def analyze(
    transcript: str,
    *,
    mode: str = "solo",
    meta: dict | None = None,
    refinement: dict | None = None,
    context: str | None = None,
    verify: bool = False,
    provider,
    emit=None,
    should_cancel=None,
    on_progress=None,
    on_step=None,
) -> Analysis:
    text = transcript
    if _needs_summary(transcript, provider):
        text = _summarize_long(transcript, provider, emit=emit, should_cancel=should_cancel)

    # Usa chat_json_stream se disponibile (streaming con on_progress), altrimenti fallback a chat_json.
    # Contratto: il fallback mantiene compatibilità con provider che non implementano lo streaming
    # (es. fake nei test). On_progress riceve il testo grezzo accumulato.
    if hasattr(provider, "chat_json_stream") and on_progress:
        raw = provider.chat_json_stream(
            prompts.build_system(),
            prompts.build_user(text, mode=mode, meta=meta, refinement=refinement, context=context),
            json_schema=Analysis.model_json_schema(),
            on_delta=on_progress,
            should_cancel=should_cancel,
        )
    else:
        raw = provider.chat_json(
            prompts.build_system(),
            prompts.build_user(text, mode=mode, meta=meta, refinement=refinement, context=context),
            json_schema=Analysis.model_json_schema(),
        )

    # Difesa: un LLM locale può restituire una lista/valore non-oggetto nonostante il prompt.
    # Senza guard, Analysis.model_validate solleverebbe un errore pydantic criptico; così
    # l'errore è chiaro e la pipeline lo mappa a status=error con un messaggio leggibile.
    if not isinstance(raw, dict):
        raise LLMError("L'analisi LLM non ha restituito un oggetto JSON (risposta inattesa del modello).")
    analysis = Analysis.model_validate(raw)
    # Comprensione-prima (Task 8): secondo passo opzionale "ho colto il punto?". Gated per non
    # raddoppiare i tempi su CPU quando il primo passo è già buono (vedi _coverage_needed).
    if verify and _coverage_needed(analysis, mode):
        if on_step:
            on_step("verify")
        analysis = _verify_coverage(
            text, analysis, mode=mode, context=context, provider=provider, should_cancel=should_cancel
        )
    return analysis


def _coverage_needed(analysis: Analysis, mode: str) -> bool:
    """Secondo passo solo se serve: purpose debole (vuoto) o riunione (le decisioni condivise
    pesano). Evita di raddoppiare i tempi quando il primo passo ha già colto il punto."""
    return not analysis.purpose.strip() or mode in ("meeting", "riunione")


def _verify_coverage(text: str, analysis: Analysis, *, mode, context, provider, should_cancel=None) -> Analysis:
    """Rilegge la trascrizione e corregge purpose + voci mancanti. Tollerante: su cancel o
    risposta inattesa tiene la prima analisi (non peggiora mai)."""
    if should_cancel and should_cancel():
        return analysis
    raw = provider.chat_json(
        prompts.build_verify_system(),
        prompts.build_verify_user(text, analysis, mode=mode, context=context),
        json_schema=Analysis.model_json_schema(),
    )
    if not isinstance(raw, dict):
        return analysis
    try:
        return Analysis.model_validate(raw)
    except Exception:
        return analysis
