"""Transcript -> Analysis (un JSON). Fallback chunk-summarize solo per testi enormi.

Soglia generosa: la trascrizione intera va in un'unica chiamata (spec §7); il
chunk-and-merge annacqua le decisioni, quindi è solo un paracadute oltre ~100k token.
"""

import re

from vokari import i18n
from vokari.analyze import figures, fit, prompts
from vokari.analyze.schema import Analysis
from vokari.llm.base import LLMError

FALLBACK_WORD_THRESHOLD = 70000  # paracadute assoluto (proxy parole) per provider senza budget


def is_sparse_analysis(analysis: Analysis) -> bool:
    """True se l'analisi non porta alcun contenuto STRUTTURATO: key_ideas, decisions,
    open_questions, next_steps, entities tutte vuote. È il sintomo "stringhe piene, liste
    vuote" (ADR-038): purpose/context possono essere pieni ma il briefing resta privo di
    sostanza. Puro (nessun LLM/IO): usato dalla pipeline per avvisare invece di consegnare
    in silenzio un briefing pieno di "(nessuna…)"."""
    return not (
        analysis.key_ideas or analysis.decisions or analysis.open_questions or analysis.next_steps or analysis.entities
    )


# --- Analisi "accorciata" (non vuota) ----------------------------------------------------
# Un modello piccolo raramente crolla: si FERMA PRIMA. Tiene 2 domande su 5, salta meta'
# delle idee, e consegna un briefing che SEMBRA completo. is_sparse_analysis() non lo vede
# (le liste non sono vuote), quindi l'utente non viene avvisato di nulla.
#
# Soglia calibrata sui gold reali del repo (elementi strutturati / parole di trascritto):
#   nota-solo-chiara          51 parole ->  6 elementi
#   riunione-magazzino-lotto 111 parole -> 15 elementi
#   brainstorm-sito-vendita  116 parole -> 16 elementi
#   iwa-landing-page        1162 parole -> 25 elementi
# La densita' CALA con la lunghezza (il parlato lungo e' ridondante): una soglia lineare
# darebbe falsi allarmi su ogni registrazione lunga. Usiamo una radice quadrata, che sui
# quattro gold lascia un margine di 1.5-3x, e giudichiamo solo sopra _THIN_MIN_WORDS —
# sotto, la varianza e' troppo alta per dire qualcosa di sensato.
_THIN_MIN_WORDS = 400
_THIN_K = 0.4


def structured_element_count(analysis: Analysis) -> int:
    """Quanti elementi strutturati porta l'analisi (le 5 liste). Puro."""
    return (
        len(analysis.key_ideas)
        + len(analysis.decisions)
        + len(analysis.open_questions)
        + len(analysis.next_steps)
        + len(analysis.entities)
    )


def expected_element_floor(transcript_words: int) -> int:
    """Minimo di elementi sotto il quale l'analisi e' sospettosamente magra per quella
    lunghezza di trascritto. Puro, sublineare (vedi calibrazione sopra)."""
    if transcript_words < _THIN_MIN_WORDS:
        return 0
    return max(3, int(_THIN_K * (transcript_words**0.5)))


def is_thin_analysis(analysis: Analysis, transcript_words: int) -> bool:
    """True se l'analisi non e' vuota ma porta molto meno di quanto la trascrizione
    conterrebbe. E' un rilevatore GROSSOLANO di scarsita', non una misura di correttezza:
    dice "forse hai perso contenuto", mai "questo e' sbagliato". Puro (nessun LLM/IO)."""
    if is_sparse_analysis(analysis):
        return False  # gia' coperto dall'avviso piu' severo
    floor = expected_element_floor(transcript_words)
    return bool(floor) and structured_element_count(analysis) < floor


# --- Analisi a finestre (map-reduce) -----------------------------------------------------
# Misurato su una registrazione reale (910 parole, qwen2.5:7b, 2026-09-22):
#   tutto in un colpo -> 7 elementi in 108s; a finestre di 350 parole -> 21 elementi in 132s.
# Le cose perse erano tutte nella SECONDA META' del testo (una data di presentazione, una
# proiezione su un mercato estero, due macro-sezioni dette esplicitamente): non erano state
# sbagliate, non erano proprio state guardate. E' il "lost in the middle": il problema non e'
# il contesto — 910 parole stanno larghe nei 32k di qwen — ma l'ATTENZIONE. Dare meno testo
# per volta costa il 22% di tempo in piu' e rende il triplo.
ANALYSIS_WINDOW_WORDS = 350
ANALYSIS_WINDOW_OVERLAP = 60
# Sotto questa soglia una passata sola basta (sui casi brevi il modello tiene tutto) e le
# finestre aggiungerebbero solo latenza e frammentazione.
ANALYSIS_WINDOW_MIN_WORDS = 400


def split_windows(text: str, *, window: int | None = None, overlap: int | None = None) -> list[str]:
    """Finestre di parole con sovrapposizione, per non perdere cio' che cade sul confine.
    Puro. L'overlap e' clampato a meta' finestra (come chunking.split_wav, ADR-055): senza
    il clamp un overlap >= window darebbe passo <= 0 e un ciclo infinito."""
    words = text.split()
    win = window or ANALYSIS_WINDOW_WORDS
    if win <= 0 or not words:
        return [text] if text.strip() else []
    ov = ANALYSIS_WINDOW_OVERLAP if overlap is None else overlap
    ov = max(0, min(ov, win // 2))
    step = win - ov
    out = [" ".join(words[i : i + win]) for i in range(0, max(1, len(words) - ov), step)]
    return [w for w in out if w.strip()]


def _norm_key(s: str) -> str:
    """Chiave di confronto per il dedup deterministico: minuscolo, senza punteggiatura ne'
    spazi doppi. Riconosce le ripetizioni letterali (che l'overlap produce di sicuro), NON
    quelle riformulate — a quelle pensa il consolidamento LLM."""
    return re.sub(r"[^0-9a-zà-ÿ ]+", "", s.lower()).strip()


# Pronomi e parole vuote che i modelli piccoli marcano come "persona" (visto in produzione:
# `io`, `rivenditore`, `negozietto` fra le "Entita' citate" del briefing). Non e' un problema
# di modello — ne' qwen2.5:7b ne' granite4.2:8b le ripuliscono nel consolidamento — ma di
# verifica: in italiano un nome proprio e' MAIUSCOLO, e "io" non e' nessuno.
_PRONOUNS = {
    "io",
    "tu",
    "lui",
    "lei",
    "noi",
    "voi",
    "loro",
    "me",
    "te",
    "se",
    "ci",
    "vi",
    "i",
    "you",
    "he",
    "she",
    "we",
    "they",
    "it",
}


# Quanti caratteri iniziali devono combaciare per considerare un'entita' "detta davvero".
# Non pretendiamo l'uguaglianza: Whisper scrive "Pierpao", l'LLM puo' normalizzare in
# "Pierpaolo" — e buttarlo via sarebbe peggio del male che curiamo.
_GROUNDING_PREFIX = 5


def _is_grounded(name: str, transcript_low: str) -> bool:
    """L'entita' compare nella trascrizione? Confronto tollerante sul prefisso, per non
    punire le normalizzazioni dell'LLM."""
    n = name.strip().lower()
    if not n:
        return False
    if n in transcript_low:
        return True
    head = n[:_GROUNDING_PREFIX]
    return len(head) >= 3 and head in transcript_low


def clean_entities(analysis: Analysis, transcript: str = "") -> Analysis:
    """Toglie i pronomi dalle entita' e declassa a `termine` i nomi comuni marcati come
    persona (un nome proprio italiano inizia maiuscolo). Con `transcript`, scarta anche le
    entita' che nella registrazione NON compaiono: misurato su un caso reale, granite4.2:8b
    ha prodotto due persone ("Sara", "Luca") che nessuno aveva mai nominato. Un'entita' e'
    per definizione qualcosa che e' stato DETTO — se non c'e' nel testo, non c'era.

    Puro, conservativo: declassa invece di cancellare dove puo', e senza trascrizione si
    comporta come prima. Muta e restituisce lo stesso oggetto."""
    low = " ".join((transcript or "").lower().split())
    kept = []
    for e in analysis.entities:
        name = (e.name or "").strip()
        if not name or name.lower() in _PRONOUNS:
            continue
        if low and not _is_grounded(name, low):
            continue  # non e' mai stata nominata: e' un'invenzione del modello
        if e.type == "persona" and not name[0].isupper():
            e.type = "termine"
        kept.append(e)
    analysis.entities = kept
    return analysis


def merge_analyses(parts: list[Analysis]) -> Analysis:
    """Unione grezza delle analisi delle finestre: liste concatenate e deduplicate per testo
    normalizzato, `meta`/`purpose`/`context` dal primo pezzo che li ha valorizzati. Puro.
    E' anche il FALLBACK quando il consolidamento LLM non riesce: grezzo ma completo — mai
    perdere contenuto per colpa di un passaggio di rifinitura (ADR-041)."""
    out = Analysis()
    seen: dict[str, set] = {}

    def _keep(field: str, item, key: str) -> bool:
        k = _norm_key(key)
        if not k:
            return False
        bucket = seen.setdefault(field, set())
        if k in bucket:
            return False
        bucket.add(k)
        getattr(out, field).append(item)
        return True

    for part in parts:
        if not out.meta.title and part.meta.title:
            out.meta = part.meta
        if not out.purpose.strip() and part.purpose.strip():
            out.purpose = part.purpose
        if not out.context.strip() and part.context.strip():
            out.context = part.context
        for idea in part.key_ideas:
            _keep("key_ideas", idea, idea)
        for dec in part.decisions:
            _keep("decisions", dec, f"{dec.title} {dec.decision}")
        for q in part.open_questions:
            _keep("open_questions", q, q)
        for st in part.next_steps:
            _keep("next_steps", st, st.task)
        for ent in part.entities:
            _keep("entities", ent, ent.name)
    return out


# Fonte unica delle costanti di chunk in fit.py; alias a livello modulo perché i test
# monkeypatchano `analyzer.SUMMARY_CHUNK_WORDS` e `_summarize_long` legge il globale del modulo.
SUMMARY_CHUNK_WORDS = fit.SUMMARY_CHUNK_WORDS


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


def _summarize_long(transcript: str, provider, *, emit=None, should_cancel=None, language: str = "it") -> str:
    words = transcript.split()
    chunks = [" ".join(words[i : i + SUMMARY_CHUNK_WORDS]) for i in range(0, len(words), SUMMARY_CHUNK_WORDS)]
    # Trascrizione enorme (~8h): N chiamate LLM in serie. Avvisa (riusa l'evento `warning`,
    # niente nuovo evento → no drift di contratto) e onora la cancellazione tra un chunk e
    # l'altro: senza, l'utente resterebbe minuti senza feedback né modo di fermare.
    if emit:
        emit("warning", {"messages": [i18n.t("analyzer.summary_warning", language, n=len(chunks))]})
    sys_summary = i18n.t("analyzer.summary_system", language)
    summaries: list[str] = []
    for i, c in enumerate(chunks):
        if should_cancel and should_cancel():
            break
        summaries.append(provider.chat_text(sys_summary, f"Porzione {i + 1}/{len(chunks)}:\n\n{c}"))
    return "\n\n---\n\n".join(summaries)


def _analyze_once(
    text: str,
    *,
    mode,
    meta,
    refinement,
    context,
    markers,
    provider,
    should_cancel,
    on_progress,
    language,
    user_context,
) -> Analysis:
    """Una singola estrazione transcript->Analysis. E' il corpo storico di analyze(), estratto
    perche' ora puo' essere invocato una volta sola (testi brevi) o una volta per finestra."""
    # Usa chat_json_stream se disponibile (streaming con on_progress), altrimenti fallback a chat_json.
    # Contratto: il fallback mantiene compatibilità con provider che non implementano lo streaming
    # (es. fake nei test). On_progress riceve il testo grezzo accumulato.
    args = {
        "mode": mode,
        "meta": meta,
        "refinement": refinement,
        "context": context,
        "markers": markers,
        "language": language,
        "user_context": user_context,
    }
    if hasattr(provider, "chat_json_stream") and on_progress:
        raw = provider.chat_json_stream(
            prompts.build_system(language, user_context),
            prompts.build_user(text, **args),
            json_schema=Analysis.model_json_schema(),
            on_delta=on_progress,
            should_cancel=should_cancel,
        )
    else:
        raw = provider.chat_json(
            prompts.build_system(language, user_context),
            prompts.build_user(text, **args),
            json_schema=Analysis.model_json_schema(),
        )

    # Difesa: un LLM locale può restituire una lista/valore non-oggetto nonostante il prompt.
    # Senza guard, Analysis.model_validate solleverebbe un errore pydantic criptico; così
    # l'errore è chiaro e la pipeline lo mappa a status=error con un messaggio leggibile.
    if not isinstance(raw, dict):
        raise LLMError("L'analisi LLM non ha restituito un oggetto JSON (risposta inattesa del modello).")
    return Analysis.model_validate(raw)


def _consolidate(
    merged: Analysis,
    *,
    mode,
    context,
    provider,
    should_cancel=None,
    language: str = "it",
    user_context: str = "",
) -> Analysis:
    """Il "reduce": una chiamata CORTA (riceve gli elementi, non la trascrizione) che unisce i
    duplicati riformulati, rimette le voci nella categoria giusta e scrive purpose/context
    globali. Tollerante per principio (ADR-041): su cancel, errore o risposta inattesa torna
    l'unione grezza — un passo di rifinitura non deve mai far perdere contenuto gia' estratto.
    Se svuotasse l'analisi, l'unione grezza vince comunque."""
    if should_cancel and should_cancel():
        return merged
    try:
        raw = provider.chat_json(
            prompts.build_consolidate_system(language, user_context),
            prompts.build_consolidate_user(
                merged, mode=mode, context=context, language=language, user_context=user_context
            ),
            json_schema=Analysis.model_json_schema(),
        )
        if not isinstance(raw, dict):
            return merged
        out = Analysis.model_validate(raw)
    except Exception:
        return merged
    if is_sparse_analysis(out) and not is_sparse_analysis(merged):
        return merged
    # Il reduce puo' riordinare e accorpare, NON portarsi via i numeri: le cifre sparite nel
    # riordino tornano in coda (controllo deterministico, nessun LLM). Vedi figures.py.
    figures.restore_lost_figures(merged, out)
    return out


def _analyze_windowed(
    text: str,
    *,
    mode,
    meta,
    refinement,
    context,
    markers,
    provider,
    should_cancel,
    on_progress,
    on_step,
    language,
    user_context,
    consolidate_provider=None,
    on_stage=None,
) -> Analysis:
    """Map-reduce: una estrazione per finestra sovrapposta, poi consolidamento.
    Una finestra che fallisce non ferma le altre (meglio un'analisi parziale che nessuna);
    se falliscono tutte, l'errore risale al chiamante come prima."""
    windows = split_windows(text)
    parts: list[Analysis] = []
    last_error: Exception | None = None
    for i, chunk in enumerate(windows):
        if should_cancel and should_cancel():
            break
        if on_step:
            on_step(f"window:{i + 1}/{len(windows)}")
        try:
            parts.append(
                _analyze_once(
                    chunk,
                    mode=mode,
                    meta=meta,
                    refinement=refinement,
                    context=context,
                    markers=markers,
                    provider=provider,
                    should_cancel=should_cancel,
                    on_progress=on_progress,
                    language=language,
                    user_context=user_context,
                )
            )
        except Exception as e:  # una finestra persa non vale l'intera analisi
            last_error = e
    if not parts:
        if last_error:
            raise last_error
        return Analysis()
    merged = merge_analyses(parts)
    # `on_stage` e' il gancio di MISURA (evals/fidelity): espone l'unione grezza e il
    # consolidato senza costringere nessuno a riscrivere la catena per osservarla.
    if on_stage:
        on_stage("merged", merged.model_copy(deep=True))
    if len(parts) == 1 or (should_cancel and should_cancel()):
        return merged
    if on_step:
        on_step("consolidate")
    out = _consolidate(
        merged,
        mode=mode,
        context=context,
        # Il reduce puo' girare su un modello diverso (ADR-066): e' UNA chiamata corta per
        # sessione, quindi li' un modello lento ma piu' capace si ripaga.
        provider=consolidate_provider or provider,
        should_cancel=should_cancel,
        language=language,
        user_context=user_context,
    )
    if on_stage:
        on_stage("consolidated", out.model_copy(deep=True))
    return out


def analyze(
    transcript: str,
    *,
    mode: str = "solo",
    meta: dict | None = None,
    refinement: dict | None = None,
    context: str | None = None,
    markers: list[dict] | None = None,
    verify: bool = False,
    provider,
    emit=None,
    should_cancel=None,
    on_progress=None,
    on_step=None,
    language: str = "it",
    user_context: str = "",
    windowed: bool = True,
    consolidate_provider=None,
    on_stage=None,
) -> Analysis:
    text = transcript
    if _needs_summary(transcript, provider):
        text = _summarize_long(transcript, provider, emit=emit, should_cancel=should_cancel, language=language)

    common = {
        "mode": mode,
        "meta": meta,
        "refinement": refinement,
        "context": context,
        "markers": markers,
        "provider": provider,
        "should_cancel": should_cancel,
        "on_progress": on_progress,
        "language": language,
        "user_context": user_context,
    }
    # Sopra la soglia il testo si analizza a finestre: dargli tutto in un colpo fa perdere
    # la seconda meta' della registrazione (vedi la misura in testa al modulo).
    was_windowed = windowed and len(text.split()) >= ANALYSIS_WINDOW_MIN_WORDS
    if was_windowed:
        analysis = _analyze_windowed(
            text, on_step=on_step, consolidate_provider=consolidate_provider, on_stage=on_stage, **common
        )
    else:
        analysis = _analyze_once(text, **common)

    # Comprensione-prima (Task 8): secondo passo opzionale "ho colto il punto?". Gated per non
    # raddoppiare i tempi su CPU quando il primo passo è già buono (vedi _coverage_needed).
    # ...ma MAI dopo le finestre: il verify rimanderebbe tutto il testo in una chiamata sola,
    # riaprendo il "lost in the middle" che le finestre hanno appena chiuso (ADR-064) e
    # costando un'altra passata intera su CPU. Li' la rifinitura la fa gia' `_consolidate`.
    if verify and not was_windowed and _coverage_needed(analysis, mode):
        if on_step:
            on_step("verify")
        analysis = _verify_coverage(
            text,
            analysis,
            mode=mode,
            context=context,
            provider=provider,
            should_cancel=should_cancel,
            language=language,
            user_context=user_context,
        )
    # Ultimo passaggio su OGNI percorso (finestre o passata singola): quello che esce di qui
    # finisce nel briefing sotto "Entita' citate", e "io (persona)" non ci deve arrivare.
    # `transcript` (non `text`): il grounding va fatto su cio' che e' stato DETTO, non su un
    # eventuale riassunto intermedio, che potrebbe aver perso il nome per strada.
    return clean_entities(analysis, transcript)


def _coverage_needed(analysis: Analysis, mode: str) -> bool:
    """Secondo passo solo se serve: purpose debole (vuoto) o riunione (le decisioni condivise
    pesano). Evita di raddoppiare i tempi quando il primo passo ha già colto il punto."""
    return not analysis.purpose.strip() or mode in ("meeting", "riunione")


def _verify_coverage(
    text: str,
    analysis: Analysis,
    *,
    mode,
    context,
    provider,
    should_cancel=None,
    language: str = "it",
    user_context: str = "",
) -> Analysis:
    """Rilegge la trascrizione e corregge purpose + voci mancanti. Tollerante: su cancel o
    risposta inattesa tiene la prima analisi (non peggiora mai)."""
    if should_cancel and should_cancel():
        return analysis
    try:
        raw = provider.chat_json(
            prompts.build_verify_system(language, user_context),
            prompts.build_verify_user(
                text, analysis, mode=mode, context=context, language=language, user_context=user_context
            ),
            json_schema=Analysis.model_json_schema(),
        )
        if not isinstance(raw, dict):
            return analysis
        out = Analysis.model_validate(raw)
    except Exception:
        # Un passo OPZIONALE non deve mai far perdere l'analisi gia' estratta: senza questo
        # un provider che cade qui manda l'intero job in error.
        return analysis
    if is_sparse_analysis(out) and not is_sparse_analysis(analysis):
        return analysis  # stessa guardia di _consolidate: il verify non puo' impoverire
    return out
