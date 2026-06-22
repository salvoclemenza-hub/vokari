"""Prompt per l'analisi della trascrizione -> JSON strutturato (spec §7)."""

from vokari.analyze.schema import Analysis

_SYSTEM = (
    "Sei un analista esperto che trasforma trascrizioni vocali di un magazzino alimentare "
    "B2B in conoscenza strutturata. Conosci la terminologia del dominio: lotti VMM, "
    "processi MAC (lavorazione), OBB (obbligo), DDT, HACCP, resa, miscelazione, scarti, "
    "tracciabilità, distinta base. "
    "Rispondi ESCLUSIVAMENTE con un JSON valido conforme allo schema richiesto: "
    "nessun testo prima o dopo, nessun code fence markdown, nessuna spiegazione. "
    "Usa l'italiano nei contenuti."
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
    "1-2 frasi): cosa si doveva decidere o capire, anche se non detto esplicitamente; NON confondere "
    "lo scopo con un dettaglio di superficie ricorrente. POI estrai decisioni, partecipanti e ruoli, "
    "action item con responsabile e scadenza, domande aperte e numeri. Per le decisioni e i next step "
    "importanti àncora brevemente al contenuto della trascrizione (parafrasi breve, non citazione "
    "obbligatoria); non gonfiare un dettaglio secondario a scopo principale. "
    'Le key_ideas devono essere FRASI COMPLETE e informative (es. "Aggiungere una galleria foto '
    'dei prodotti per la clientela multilingua"), non etichette di 1-2 parole (es. "Galleria").'
)

_SHAPE = """Produci ESATTAMENTE questo JSON (chiavi in inglese, valori in italiano):
{
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

# Esempio few-shot con terminologia aziendale specifica del dominio.
# Stabilizza la lingua (italiano) e la granularità dei campi su modelli locali (Ollama).
_FEWSHOT = """
Esempio di trascrizione e JSON atteso per il tuo dominio:

TRASCRIZIONE: "Oggi abbiamo ricevuto il lotto VMM-2026-1234 dal fornitore Rossi. Il MAC ha rilevato una non conformità sulla resa delle acciughe: 87% invece del 95% atteso. Decidiamo di bloccare il lotto e avvisare il Responsabile Qualità entro domani. Mario si occupa della segnalazione HACCP."

JSON ATTESO:
{
  "meta": {"type": "meeting", "title": "Non conformità lotto VMM-2026-1234", "participants": ["Mario"], "duration_min": 15, "date": ""},
  "purpose": "Decidere come gestire la non conformità di resa sul lotto VMM-2026-1234: bloccarlo e definire chi avvisa.",
  "context": "Riunione operativa per gestire una non conformità rilevata dal MAC sul lotto VMM-2026-1234: resa acciughe 87% vs 95% atteso.",
  "key_ideas": ["Resa MAC sotto soglia: 87% vs 95%", "Lotto bloccato in attesa di verifica Responsabile Qualità"],
  "decisions": [{"title": "Blocco lotto VMM-2026-1234", "decision": "Il lotto è bloccato fino a verifica", "rationale": "Non conformità resa MAC oltre la tolleranza"}],
  "open_questions": ["La non conformità richiede segnalazione all'autorità sanitaria?"],
  "next_steps": [{"task": "Segnalazione HACCP non conformità", "owner": "Mario", "deadline": null}],
  "entities": [
    {"name": "VMM-2026-1234", "type": "termine", "note": "lotto bloccato"},
    {"name": "Mario", "type": "persona", "note": "responsabile segnalazione"},
    {"name": "MAC", "type": "termine", "note": "processo di lavorazione"}
  ]
}"""


def build_system() -> str:
    return _SYSTEM


def build_user(
    transcript: str,
    *,
    mode: str = "solo",
    meta: dict | None = None,
    refinement: dict | None = None,
    context: str | None = None,
) -> str:
    parts = [_FOCUS[_MODE_ALIASES.get(mode, "solo")], "", _GUIDANCE, "", _SHAPE, _FEWSHOT, ""]
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
    parts.append("TRASCRIZIONE:")
    parts.append(transcript)
    return "\n".join(parts)


# --- Check di copertura (Task 8): secondo passo "ho colto il punto?" -----------------------
_VERIFY_SYSTEM = (
    "Sei un revisore severo: verifichi se un'analisi cattura il PUNTO PRINCIPALE (lo scopo o la "
    "decisione centrale) di una sessione e la correggi se serve. Rispondi ESCLUSIVAMENTE con un JSON "
    "Analysis valido, nessun code fence, nessuna spiegazione. Usa l'italiano nei contenuti."
)


def build_verify_system() -> str:
    return _VERIFY_SYSTEM


def build_verify_user(transcript: str, analysis: Analysis, *, mode: str = "solo", context: str | None = None) -> str:
    parts = [
        "Rileggi la TRASCRIZIONE e l'ANALISI CORRENTE qui sotto.",
        "Qual è il PUNTO PRINCIPALE (lo scopo o la decisione centrale) della sessione?",
        "Se l'analisi NON lo cattura nel campo `purpose` (vuoto, generico, o un dettaglio di superficie), "
        "CORREGGILA: valorizza `purpose` con lo scopo vero e aggiungi le decisioni / next step IMPORTANTI "
        "mancanti. Non rimuovere informazioni corrette già presenti. Ritorna l'oggetto Analysis JSON COMPLETO aggiornato.",
        "",
    ]
    if context:
        parts += ["CONTESTO FORNITO DALL'UTENTE (lo scopo dichiarato):", context, ""]
    parts += [_SHAPE, "", "ANALISI CORRENTE (JSON):", analysis.model_dump_json(), "", "TRASCRIZIONE:", transcript]
    return "\n".join(parts)
