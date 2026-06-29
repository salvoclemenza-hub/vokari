"""Prompt per l'analisi della trascrizione -> JSON strutturato (spec §7).

La lingua dell'OUTPUT (i valori del JSON) è guidata da `language` (it|en = `app_language`), non
dalla lingua dell'audio: l'LLM produce i contenuti nella lingua dell'app. Le ISTRUZIONI del
prompt restano in italiano (l'LLM le comprende); cambia solo la direttiva sulla lingua dei valori.
"""

from vokari import i18n
from vokari import markers as markers_mod
from vokari.analyze.schema import Analysis

# Budget ragionevole per user_context nei prompt (spec §4): evita bloat dei token
_USER_CONTEXT_MAX_CHARS = 500


def _truncate_user_context(uc: str) -> str:
    """Trunca user_context a lunghezza ragionevole con indicatore visivo se tagliato."""
    uc = (uc or "").strip()
    if len(uc) <= _USER_CONTEXT_MAX_CHARS:
        return uc
    return uc[: _USER_CONTEXT_MAX_CHARS - 3] + "..."


# Base del system prompt SENZA la direttiva di lingua (appesa da build_system in base a `language`).
_SYSTEM = (
    "Sei un analista esperto che trasforma trascrizioni vocali (riunioni, brainstorming, "
    "note a voce) in conoscenza strutturata, chiara e azionabile. "
    "Rispondi ESCLUSIVAMENTE con un JSON valido conforme allo schema richiesto: "
    "nessun testo prima o dopo, nessun code fence markdown, nessuna spiegazione."
)

_FOCUS = {
    "meeting": "È una RIUNIONE tra più persone: privilegia decisioni condivise, "
    "responsabilità (owner) e prossimi passi concordati.",
    "solo": "È un BRAINSTORM in solitaria di una persona: privilegia idee, intuizioni "
    "e prossimi passi personali; participants resta vuoto.",
}

# Il valore canonico di `mode` lato UI/settings è 'solo'|'riunione' (italiano), mentre
# il focus e meta.type usano 'meeting'. Normalizziamo qui così entrambi i nomi mappano
# allo stesso focus (senza questo, mode='riunione' cadeva nel fallback 'solo').
_MODE_ALIASES = {"meeting": "meeting", "riunione": "meeting", "solo": "solo"}

# Comprensione-prima: guida il modello a individuare PRIMA lo scopo/decisione principale, poi il
# resto, con grounding leggero (parafrasi, non citazioni obbligatorie). Riduce il fissarsi su un
# dettaglio di superficie (es. caso IWA: "calendario di raccolta" invece della decisione landing page).
_GUIDANCE = (
    "Procedi così: PRIMA individua lo SCOPO/decisione principale della sessione (campo `purpose`, "
    "1-2 frasi). Chiediti: 'PERCHÉ è avvenuta questa sessione? Qual era la DOMANDA o la DECISIONE "
    "al centro?' — cerca formulazioni esplicite come 'dobbiamo decidere se...', 'sì o no', "
    "'la risposta è...', 'vogliamo X o Y?' — spesso compaiono TARDI nella trascrizione. "
    "ATTENZIONE: l'argomento più MENZIONATO o discusso nel dettaglio (formati, strumenti, "
    "implementazioni tecniche) è tipicamente un MEZZO che serve la decisione, NON lo scopo stesso. "
    "NON spacciare un dettaglio tecnico ricorrente per lo scopo principale. "
    "POI estrai decisioni, partecipanti e ruoli, "
    "action item con responsabile e scadenza, domande aperte e numeri. Per le decisioni e i next step "
    "importanti àncora brevemente al contenuto della trascrizione (parafrasi breve, non citazione "
    "obbligatoria); non gonfiare un dettaglio secondario a scopo principale. "
    'Le key_ideas devono essere FRASI COMPLETE e informative (es. "Aggiungere una galleria foto '
    'dei prodotti per la clientela multilingua"), non etichette di 1-2 parole (es. "Galleria").'
)

_SHAPE_BODY = """{
  "meta": {"type": "<meeting|solo>", "title": "<titolo breve>", "participants": [],
           "duration_min": 0, "date": ""},
  "purpose": "<lo SCOPO/decisione principale della sessione in 1-2 frasi: cosa si doveva decidere o capire>",
  "context": "<1 paragrafo: di cosa si parlava e perché>",
  "key_ideas": ["<idea chiave: FRASE COMPLETA e informativa (soggetto+verbo), NON un'etichetta di 1-2 parole>", "..."],
  "decisions": [{"title": "<titolo>", "decision": "<cosa è stato deciso>", "rationale": "<perché>"}],
  "open_questions": ["<domanda/decisione ancora aperta>", "..."],
  "next_steps": [{"task": "<cosa fare>", "owner": "<chi|null>", "deadline": "<ISO|null>"}],
  "entities": [{"name": "<nome>", "type": "<persona|progetto|termine>", "note": "<nota>"}]
}
Se un campo non è desumibile, usa lista vuota o stringa vuota; per owner/deadline usa null."""


def _shape(language: str) -> str:
    """Header della shape JSON con la clausola di lingua dei VALORI parametrica (it|en)."""
    clause = i18n.t("prompts.values_lang", language)
    return f"Produci ESATTAMENTE questo JSON (chiavi in inglese, {clause}):\n{_SHAPE_BODY}"


# Esempio few-shot generico (nessun dominio aziendale).
# Stabilizza la lingua e la granularità dei campi su modelli locali (Ollama).
# NOTA (ADR-057): un secondo few-shot con "decisione sepolta" è stato testato (eval v4) ma ha
# causato cross-contamination su qwen2.5:7b — il modello pattern-matcha alle surface feature
# dell'esempio (es. open_question sull'invito) invece di imparare il pattern astratto MEZZO/FINE.
# Il problema IWA (decisione landing page sepolta dopo 1000 parole di calendario) è un limite
# del modello 7B — risolto in produzione con context injection dell'utente.
_FEWSHOT = """
Esempio di trascrizione e JSON atteso (per granularità e formato):

TRASCRIZIONE: "Rivediamo il lancio della newsletter mensile. Sara propone una sola uscita al mese, il primo giovedì, ben curata. Decidiamo quattro sezioni fisse e rendiamo l'intervista opzionale. Luca prepara la bozza entro il venti. Resta aperto come gestire le iscrizioni di chi non è ancora membro. Per ora Marco smista le email in arrivo, ma non è sostenibile a lungo."

JSON ATTESO:
{
  "meta": {"type": "meeting", "title": "Lancio newsletter mensile", "participants": ["Sara", "Luca", "Marco"], "duration_min": 15, "date": ""},
  "purpose": "Definire formato, sezioni e responsabilità per il lancio della newsletter mensile.",
  "context": "Riunione di pianificazione per avviare una newsletter mensile: frequenza, struttura dei contenuti e gestione delle email in arrivo.",
  "key_ideas": ["Una sola uscita al mese, il primo giovedì, per privilegiare la qualità", "Quattro sezioni fisse con l'intervista resa opzionale per sostenibilità"],
  "decisions": [{"title": "Cadenza e struttura", "decision": "Newsletter mensile con quattro sezioni fisse, intervista opzionale", "rationale": "Mantenere qualità e ridurre il carico redazionale"}],
  "open_questions": ["Come gestire le iscrizioni di chi non è ancora membro?"],
  "next_steps": [{"task": "Preparare la bozza del primo numero", "owner": "Luca", "deadline": null}],
  "entities": [
    {"name": "Sara", "type": "persona", "note": "propone la cadenza mensile"},
    {"name": "Marco", "type": "persona", "note": "smista le email in arrivo"}
  ]
}"""


def build_system(language: str = "it", user_context: str = "") -> str:
    base = _SYSTEM + " " + i18n.t("prompts.content_directive", language)
    uc = _truncate_user_context(user_context)
    if uc:
        base += (
            f" Contesto dell'utente (dominio, ruolo e termini ricorrenti;"
            f" usalo per interpretare sigle e tecnicismi): {uc}"
        )
    return base


def build_user(
    transcript: str,
    *,
    mode: str = "solo",
    meta: dict | None = None,
    refinement: dict | None = None,
    context: str | None = None,
    markers: list[dict] | None = None,
    language: str = "it",
    user_context: str = "",
) -> str:
    parts = [_FOCUS[_MODE_ALIASES.get(mode, "solo")], "", _GUIDANCE, "", _shape(language), _FEWSHOT, ""]
    # Rinforzo della lingua di output vicino al testo (recency): conta su modelli locali (qwen)
    # che, col few-shot in italiano, tenderebbero a ignorare la direttiva del system.
    parts.append(i18n.t("prompts.reinforce", language))
    parts.append("")
    # user_context è iniettato sia nel system (build_system) che qui vicino alla trascrizione.
    # Stessa strategia di recency adottata per il rinforzo-lingua: i modelli locali (qwen) tendono
    # a ignorare le direttive del system prompt e beneficiano di un secondo rinforzo prossimo al testo.
    uc = _truncate_user_context(user_context)
    if uc:
        parts.append(
            "CONTESTO PERSISTENTE DELL'UTENTE (dominio, ruolo, termini ricorrenti;"
            " usalo per interpretare sigle e tecnicismi):"
        )
        parts.append(uc)
        parts.append("")
    if context:
        parts.append("CONTESTO FORNITO DALL'UTENTE (usalo per capire lo SCOPO della sessione):")
        parts.append(context)
        parts.append("")
    if meta:
        known = [f"- {k}: {v}" for k, v in meta.items() if v not in (None, "", [], 0)]
        if known:
            parts.append("Metadati noti (usali per popolare il campo meta):")
            parts.extend(known)
            parts.append("")
    if refinement:
        parts.append("Contesto aggiuntivo fornito dall'utente (usalo per arricchire):")
        for q, a in refinement.items():
            parts.append(f"- D: {q}\n  R: {a}")
        parts.append("")
    mk_lines = markers_mod.marker_lines(markers)
    if mk_lines:
        parts.append(
            "SEGNALIBRI INSERITI DALL'UTENTE durante la registrazione (momenti marcati come "
            "importanti; dai priorità a questi punti nell'individuare scopo, decisioni e key_ideas):"
        )
        parts.extend(mk_lines)
        parts.append("")
    parts.append("TRASCRIZIONE:")
    parts.append(transcript)
    return "\n".join(parts)


# --- Check di copertura (Task 8): secondo passo "ho colto il punto?" -----------------------
# Base SENZA direttiva di lingua (appesa da build_verify_system in base a `language`).
_VERIFY_SYSTEM = (
    "Sei un revisore severo: verifichi se un'analisi cattura il PUNTO PRINCIPALE (lo scopo o la "
    "decisione centrale) di una sessione e la correggi se serve. Rispondi ESCLUSIVAMENTE con un JSON "
    "Analysis valido, nessun code fence, nessuna spiegazione."
)


def build_verify_system(language: str = "it", user_context: str = "") -> str:
    base = _VERIFY_SYSTEM + " " + i18n.t("prompts.content_directive", language)
    uc = _truncate_user_context(user_context)
    if uc:
        base += f" Contesto dell'utente: {uc}"
    return base


def build_verify_user(
    transcript: str,
    analysis: Analysis,
    *,
    mode: str = "solo",
    context: str | None = None,
    language: str = "it",
    user_context: str = "",
) -> str:
    parts = [
        "Leggi la TRASCRIZIONE in calce e svolgi questi passi:",
        "PASSO 1 — Individua INDIPENDENTEMENTE il PUNTO PRINCIPALE della sessione (cosa si doveva "
        "decidere o capire?). Cerca segnali espliciti come 'dobbiamo decidere se...', 'sì o no', "
        "'la risposta è...', 'vogliamo X o Y?' — compaiono spesso TARDI nel testo. Non fermarti "
        "all'argomento più menzionato: quello è spesso un MEZZO, non il FINE.",
        "PASSO 2 — Confronta il tuo punto principale con il campo `purpose` nell'ANALISI CORRENTE.",
        "PASSO 3 — Se il purpose attuale è vuoto, troppo generico, o descrive un MEZZO (formato, "
        "strumento, implementazione) invece della DECISIONE vera: AGGIORNA `purpose` e aggiungi "
        "le decisioni/next_step IMPORTANTI mancanti. Non rimuovere informazioni già corrette. "
        "Ritorna l'oggetto Analysis JSON COMPLETO aggiornato.",
        "",
    ]
    # Stesso rinforzo di recency usato in build_user: i modelli locali beneficiano
    # del user_context vicino alla trascrizione, non solo nel system prompt.
    uc = _truncate_user_context(user_context)
    if uc:
        parts += [
            "CONTESTO PERSISTENTE DELL'UTENTE (dominio, ruolo, termini ricorrenti;"
            " usalo per interpretare sigle e tecnicismi):",
            uc,
            "",
        ]
    if context:
        parts += ["CONTESTO FORNITO DALL'UTENTE (lo scopo dichiarato):", context, ""]
    parts += [
        _shape(language),
        "",
        i18n.t("prompts.reinforce", language),
        "",
        "TRASCRIZIONE (leggi prima questa):",
        transcript,
        "",
        "ANALISI CORRENTE (confronta il `purpose` con quanto trovato nella TRASCRIZIONE):",
        analysis.model_dump_json(),
    ]
    return "\n".join(parts)
