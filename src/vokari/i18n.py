"""Catalogo i18n del MOTORE (lato Python).

Speculare a `frontend/src/i18n/` ma per il backend: una sola fonte di verità per le
stringhe fisse degli artefatti (briefing/recap/obsidian), le direttive di lingua dei prompt
LLM e i messaggi della pipeline.

`app_language` (it|en) decide la lingua di TUTTO l'output generato dal motore. È **separato**
da `transcription_language` (lingua dell'audio): l'LLM produce l'output nella lingua dell'app
a prescindere dalla lingua parlata nella registrazione.

Strategia anti-regressione: i valori "it" sono **verbatim** alle stringhe originali del codice
→ con lingua di default "it" l'output è identico e i test esistenti restano verdi.
"""

from __future__ import annotations

DEFAULT_LANG = "it"
SUPPORTED_LANGS = ("it", "en")

# Chiave -> {it, en}. I valori possono contenere placeholder {nome} interpolati da t(**kwargs).
_CATALOG: dict[str, dict[str, str]] = {
    # ── comune (riusato da più renderer) ──
    "common.session_fallback": {"it": "Sessione", "en": "Session"},
    "common.na": {"it": "(non disponibile)", "en": "(not available)"},
    "common.why_inline": {"it": "perché", "en": "why"},
    "common.by_inline": {"it": "entro", "en": "by"},
    "common.to_clarify_h": {"it": "Punti da chiarire", "en": "Points to clarify"},
    "common.bookmarks_h": {"it": "Segnalibri", "en": "Bookmarks"},
    # ── briefing.md ──
    "briefing.purpose_h": {"it": "Scopo della sessione", "en": "Session purpose"},
    "briefing.context_h": {"it": "Contesto", "en": "Context"},
    "briefing.decisions_h": {"it": "Decisioni prese", "en": "Decisions made"},
    "briefing.decisions_empty": {"it": "(nessuna decisione registrata)", "en": "(no decisions recorded)"},
    "briefing.summary_h": {"it": "Sintesi", "en": "Summary"},
    "briefing.no_key_ideas": {"it": "(nessuna idea chiave)", "en": "(no key ideas)"},
    "briefing.entities_label": {"it": "Entità citate:", "en": "Entities mentioned:"},
    "briefing.open_questions_h": {"it": "Domande aperte", "en": "Open questions"},
    "briefing.none": {"it": "(nessuna)", "en": "(none)"},
    "briefing.to_clarify": {"it": "DA CHIARIRE", "en": "TO CLARIFY"},
    "briefing.next_steps_h": {"it": "Prossimi passi", "en": "Next steps"},
    "briefing.no_next_steps": {"it": "(nessun prossimo passo)", "en": "(no next steps)"},
    "briefing.markers_h": {
        "it": "Segnalibri (momenti marcati dall'utente durante la registrazione)",
        "en": "Bookmarks (moments you marked during the recording)",
    },
    "briefing.transcript_h": {
        "it": "Trascrizione integrale (ground truth)",
        "en": "Full transcript (ground truth)",
    },
    "briefing.instr_meeting": {
        "it": (
            "Briefing di una riunione. Parti dalle decisioni prese e dalle open_questions; "
            "usa context e next_steps per coordinare i follow-up."
        ),
        "en": (
            "Briefing of a meeting. Start from the decisions made and the open_questions; "
            "use context and next_steps to coordinate the follow-ups."
        ),
    },
    "briefing.instr_solo": {
        "it": (
            "Briefing di un brainstorm individuale. Parti dalle key_ideas e dalle open_questions; "
            "usa next_steps come lista d'azione personale."
        ),
        "en": (
            "Briefing of a solo brainstorm. Start from the key_ideas and the open_questions; "
            "use next_steps as a personal action list."
        ),
    },
    # ── recap.md ──
    "recap.in_short_h": {"it": "In breve", "en": "In short"},
    "recap.no_summary": {"it": "_(nessun riassunto)_", "en": "_(no summary)_"},
    "recap.decisions_h": {"it": "Decisioni", "en": "Decisions"},
    "recap.next_steps_h": {"it": "Prossimi passi", "en": "Next steps"},
    "recap.key_discussion_h": {"it": "Discussione chiave", "en": "Key discussion"},
    "recap.open_questions_h": {"it": "Domande aperte", "en": "Open questions"},
    # ── note Obsidian ──
    "obs.key_points_h": {"it": "Punti chiave", "en": "Key points"},
    "obs.central_idea": {"it": "Idea centrale:", "en": "Central idea:"},
    "obs.decisions_h": {"it": "Decisioni", "en": "Decisions"},
    "obs.links_h": {"it": "Collegamenti", "en": "Links"},
    "obs.decision_label": {"it": "Decisione:", "en": "Decision:"},
    "obs.rationale_label": {"it": "Motivazione:", "en": "Rationale:"},
    "obs.source_label": {"it": "Fonte:", "en": "Source:"},
    "obs.tag_session": {"it": "sessione", "en": "session"},
    "obs.tag_decision": {"it": "decisione", "en": "decision"},
    # ── tipo entità (display) — lo schema mantiene l'enum IT (contratto); qui solo la resa ──
    "entity.persona": {"it": "persona", "en": "person"},
    "entity.progetto": {"it": "progetto", "en": "project"},
    "entity.termine": {"it": "termine", "en": "term"},
    # ── prompt LLM: direttiva di lingua dei contenuti ──
    "prompts.content_directive": {
        "it": "Usa l'italiano nei contenuti.",
        "en": (
            "IMPORTANT: write ALL content/values in English, regardless of the language spoken "
            "in the transcript. The JSON keys stay in English as specified."
        ),
    },
    "prompts.values_lang": {"it": "valori in italiano", "en": "values in English"},
    "prompts.reinforce": {
        "it": "Ricorda: tutti i valori del JSON in italiano.",
        "en": "Reminder: write every JSON value in English, even if the transcript is in another language.",
    },
    # ── intervista ──
    "interview.lang_directive": {
        "it": "Scrivi le domande in italiano.",
        "en": "Write the questions in English.",
    },
    "interview.skipped_marker": {
        "it": "domanda saltata in rifinitura",
        "en": "question skipped during refinement",
    },
    # ── analyzer ──
    "analyzer.summary_system": {
        "it": (
            "Riassumi in italiano questa porzione di trascrizione mantenendo "
            "decisioni, nomi, numeri e prossimi passi. Sii conciso."
        ),
        "en": (
            "Summarize this portion of the transcript in English, preserving "
            "decisions, names, numbers and next steps. Be concise."
        ),
    },
    "analyzer.summary_warning": {
        "it": (
            "Trascrizione oltre il contesto del modello: la riassumo in {n} parti prima dell'analisi "
            "(qualche minuto; il dettaglio può ridursi). Per la massima fedeltà usa un modello con "
            "contesto più ampio o dividi la registrazione."
        ),
        "en": (
            "Transcript longer than the model's context: I'll summarize it in {n} parts before the "
            "analysis (a few minutes; some detail may be lost). For maximum fidelity use a model with a "
            "wider context or split the recording."
        ),
    },
    # ── fit.py (idoneità trascrizione↔modello) ──
    "fit.rec_summarize": {
        "it": (
            "Per la massima fedeltà usa Claude (200k token di contesto) o un modello Ollama con più "
            "contesto, oppure dividi la registrazione in parti più brevi."
        ),
        "en": (
            "For maximum fidelity use Claude (200k token context) or an Ollama model with a wider "
            "context, or split the recording into shorter parts."
        ),
    },
    "fit.rec_over": {
        "it": (
            "Dividi la registrazione in parti più brevi o usa Claude (200k token): anche riassunta, "
            "questa trascrizione supererebbe il contesto del modello."
        ),
        "en": (
            "Split the recording into shorter parts or use Claude (200k token): even summarized, this "
            "transcript would exceed the model's context."
        ),
    },
    "fit.reason_ideal": {
        "it": "La trascrizione entra nel contesto del modello: analisi in una passata, fedeltà massima.",
        "en": "The transcript fits the model's context: single-pass analysis, maximum fidelity.",
    },
    "fit.reason_summarize": {
        "it": (
            "La trascrizione (~{tokens} token) supera il budget del modello (~{budget} token): "
            "verrà riassunta in {n} parti prima dell'analisi, con possibile perdita di dettaglio."
        ),
        "en": (
            "The transcript (~{tokens} tokens) exceeds the model's budget (~{budget} tokens): "
            "it will be summarized in {n} parts before the analysis, with possible loss of detail."
        ),
    },
    "fit.reason_over": {
        "it": (
            "La trascrizione (~{tokens} token) supera di molto il budget del modello (~{budget} token): "
            "neanche un riassunto in {n} parti rientrerebbe."
        ),
        "en": (
            "The transcript (~{tokens} tokens) far exceeds the model's budget (~{budget} tokens): "
            "not even a summary in {n} parts would fit."
        ),
    },
    "fit.ctx_fallback": {
        "it": " (contesto del modello non leggibile ora: stima prudente)",
        "en": " (model context not readable right now: conservative estimate)",
    },
    # ── pipeline: messaggi/warning/errori ──
    "pipeline.step_verify": {
        "it": "Ricontrollo di aver colto tutto",
        "en": "Double-checking I caught everything",
    },
    "pipeline.step_questions": {
        "it": "Preparo le domande di rifinitura",
        "en": "Preparing the refinement questions",
    },
    "pipeline.ollama_starting": {
        "it": "Ollama non era attivo: avvio automatico in corso…",
        "en": "Ollama was not running: starting it automatically…",
    },
    "pipeline.ollama_unreachable": {
        "it": (
            "Ollama non è raggiungibile e non è stato possibile avviarlo "
            "automaticamente. Avvialo manualmente o passa a Claude nelle Impostazioni."
        ),
        "en": (
            "Ollama is unreachable and could not be started automatically. "
            "Start it manually or switch to Claude in Settings."
        ),
    },
    "pipeline.model_dl_failed": {
        "it": "Impossibile scaricare il modello di trascrizione «{model}»: {err}",
        "en": "Could not download the transcription model «{model}»: {err}",
    },
    "pipeline.long_audio_turbo": {
        "it": (
            "Registrazione lunga (~{minutes} min) con «{model}»: large-v3-turbo è circa 3x più veloce a "
            "parità di qualità pratica (puoi cambiarlo in Modelli AI)."
        ),
        "en": (
            "Long recording (~{minutes} min) with «{model}»: large-v3-turbo is about 3x faster with the "
            "same practical quality (you can change it in AI Models)."
        ),
    },
    "pipeline.empty_transcript": {
        "it": "Trascrizione vuota: nessun parlato rilevato nell'audio.",
        "en": "Empty transcript: no speech detected in the audio.",
    },
    "pipeline.questions_failed": {
        "it": (
            "Non sono riuscito a preparare le domande di rifinitura (il modello è "
            "lento): salto l'intervista e genero comunque il briefing."
        ),
        "en": (
            "I couldn't prepare the refinement questions (the model is slow): "
            "I'll skip the interview and generate the briefing anyway."
        ),
    },
    "pipeline.sparse_analysis": {
        "it": (
            "L'analisi è tornata quasi vuota: nessuna idea, decisione, domanda o azione "
            "estratta dalla trascrizione. Il modello potrebbe aver faticato — prova un "
            "modello più capace, aggiungi un contesto in Home, oppure verifica che la "
            "registrazione contenga davvero contenuto da sintetizzare."
        ),
        "en": (
            "The analysis came back almost empty: no ideas, decisions, questions or actions "
            "were extracted from the transcript. The model may have struggled — try a more "
            "capable model, add some context in Home, or check that the recording actually "
            "contains content to summarize."
        ),
    },
    # lingua audio ≠ configurata (L09)
    "pipeline.lang_mismatch": {
        "it": (
            "Hai impostato la lingua «{configured}» ma l'audio sembra in {detected} (confidenza {conf}%): "
            "la trascrizione potrebbe essere degradata. Cambia la lingua in Impostazioni o usa 'auto'."
        ),
        "en": (
            "You set the language to «{configured}» but the audio seems to be in {detected} (confidence "
            "{conf}%): the transcript may be degraded. Change the language in Settings or use 'auto'."
        ),
    },
    "pipeline.lang_uncertain": {
        "it": (
            "Lingua dell'audio incerta (rilevata {detected}, confidenza {conf}%): "
            "possibile audio multilingua o di bassa qualità — la trascrizione potrebbe contenere errori."
        ),
        "en": (
            "Audio language uncertain (detected {detected}, confidence {conf}%): "
            "possibly multilingual or low-quality audio — the transcript may contain errors."
        ),
    },
    # ── app/api.py: messaggi d'errore operativi mostrati alla UI ──
    "api.no_api_key": {"it": "Nessuna chiave API impostata.", "en": "No API key set."},
    "api.key_invalid": {"it": "Chiave API non valida o scaduta.", "en": "API key invalid or expired."},
    "api.claude_unreachable": {
        "it": "Claude non raggiungibile (controlla la rete).",
        "en": "Claude unreachable (check your network).",
    },
    "api.verify_failed": {"it": "Verifica non riuscita.", "en": "Verification failed."},
    "api.ollama_unreachable_run": {
        "it": "Ollama non raggiungibile. Assicurati che sia in esecuzione.",
        "en": "Ollama unreachable. Make sure it is running.",
    },
    "api.ollama_unreachable": {"it": "Ollama non raggiungibile", "en": "Ollama unreachable"},
    "api.ollama_installed_not_started": {
        "it": "Ollama installato ma non avviato",
        "en": "Ollama installed but not started",
    },
    "api.ollama_not_started": {"it": "Ollama non avviato", "en": "Ollama not started"},
    "api.file_not_found": {
        "it": "File non trovato: potrebbe essere stato spostato o eliminato.",
        "en": "File not found: it may have been moved or deleted.",
    },
    "api.file_empty": {"it": "Il file audio è vuoto.", "en": "The audio file is empty."},
    "api.resume_file_missing": {
        "it": "File audio non trovato ('{path}'): impossibile riprendere l'elaborazione.",
        "en": "Audio file not found ('{path}'): cannot resume processing.",
    },
    "api.session_not_found": {"it": "sessione {sid} non trovata", "en": "session {sid} not found"},
    "api.job_not_found": {"it": "job {sid} non trovato", "en": "job {sid} not found"},
    "api.transcript_not_editable": {
        "it": "trascrizione non più modificabile (stato: {status})",
        "en": "transcript no longer editable (status: {status})",
    },
    "api.untitled_session": {"it": "Sessione senza titolo", "en": "Untitled session"},
    "api.vault_not_configured": {
        "it": "vault Obsidian non configurato (Impostazioni)",
        "en": "Obsidian vault not configured (Settings)",
    },
    "api.no_obsidian_note": {
        "it": "nessuna nota Obsidian disponibile per la sessione",
        "en": "no Obsidian note available for this session",
    },
    "api.invalid_url": {"it": "url non valido", "en": "invalid url"},
    "api.no_active_recording": {"it": "nessuna registrazione attiva", "en": "no active recording"},
    "api.bookmark_not_found": {"it": "segnalibro inesistente", "en": "bookmark not found"},
    "api.audio_unavailable": {"it": "audio non disponibile", "en": "audio not available"},
    "api.audio_file_missing": {
        "it": "file audio non trovato (spostato o eliminato)",
        "en": "audio file not found (moved or deleted)",
    },
    "api.disk_full": {
        "it": "Spazio su disco insufficiente per registrare (~{minutes} min disponibili). Libera spazio e riprova.",
        "en": "Not enough disk space to record (~{minutes} min available). Free up some space and try again.",
    },
    "api.disk_low": {
        "it": "Spazio su disco quasi esaurito: circa {minutes} min di registrazione disponibili.",
        "en": "Disk space almost full: about {minutes} min of recording available.",
    },
    # ── catalogo modelli (descrizioni + tag mostrati nelle card "Modelli AI") ──
    "models.off_desc": {
        "it": "Modello locale installato (fuori dal catalogo consigliato di VOKARI).",
        "en": "Local model installed (outside VOKARI's recommended catalog).",
    },
    "models.desc.qwen2.5:7b": {
        "it": "Miglior compromesso: ottimo italiano, JSON affidabile, veloce su CPU — il default.",
        "en": "Best all-rounder: great Italian, reliable JSON, fast on CPU — the default.",
    },
    "models.desc.qwen3:4b-instruct": {
        "it": "Nuova gen Qwen3: veloce, leggero, ottimo italiano; per dispositivi con poca RAM.",
        "en": "New-gen Qwen3: fast, lightweight, great Italian; for low-RAM devices.",
    },
    "models.desc.gemma3:4b-instruct": {
        "it": "Gemma3 leggero: reasoning pulito, istruzioni affidabili, multilingue.",
        "en": "Lightweight Gemma3: clean reasoning, reliable instructions, multilingual.",
    },
    "models.desc.llama3.1:8b": {
        "it": "Modello generale solido con buon italiano: alternativa validata ai Qwen.",
        "en": "Solid general model with good Italian: a proven alternative to the Qwens.",
    },
    "models.desc.qwen2.5:14b": {
        "it": "Massima qualità e ragionamento; richiede >16 GB di RAM.",
        "en": "Top quality and reasoning; requires >16 GB of RAM.",
    },
    "models.tag.italiano": {"it": "italiano", "en": "Italian"},
    "models.tag.json": {"it": "json", "en": "JSON"},
    "models.tag.veloce": {"it": "veloce", "en": "fast"},
    "models.tag.leggero": {"it": "leggero", "en": "lightweight"},
    "models.tag.multilingue": {"it": "multilingue", "en": "multilingual"},
    "models.tag.reasoning": {"it": "reasoning", "en": "reasoning"},
    "api.reexport_no_analysis": {
        "it": "Analisi non disponibile per questa sessione (creata prima dell'aggiornamento): impossibile rigenerare.",
        "en": "Analysis not available for this session (created before the update): cannot regenerate.",
    },
}

# Nome leggibile di una lingua (codice ISO) espresso in IT o EN — per i messaggi L09.
_LANG_NAMES: dict[str, dict[str, str]] = {
    "it": {"it": "italiano", "en": "Italian"},
    "en": {"it": "inglese", "en": "English"},
    "fr": {"it": "francese", "en": "French"},
    "de": {"it": "tedesco", "en": "German"},
    "es": {"it": "spagnolo", "en": "Spanish"},
    "pt": {"it": "portoghese", "en": "Portuguese"},
    "nl": {"it": "olandese", "en": "Dutch"},
}


def normalize_lang(lang: str | None) -> str:
    """Normalizza un codice lingua ('EN'→'en'); non supportata/vuota → DEFAULT_LANG."""
    code = (lang or "").lower()
    return code if code in SUPPORTED_LANGS else DEFAULT_LANG


def t(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    """Traduce `key` nella lingua `lang` (fallback IT). Chiave mancante → la chiave stessa
    (visibile come in i18next). I `kwargs` interpolano gli eventuali placeholder {nome}."""
    entry = _CATALOG.get(key)
    if entry is None:
        return key
    lang = normalize_lang(lang)
    value = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    if kwargs:
        try:
            return value.format(**kwargs)
        except (KeyError, IndexError):
            return value
    return value


def lang_name(code: str, in_lang: str = DEFAULT_LANG) -> str:
    """Nome leggibile della lingua `code`, espresso nella lingua `in_lang`. Codice ignoto → il
    codice stesso."""
    in_lang = normalize_lang(in_lang)
    names = _LANG_NAMES.get((code or "").lower())
    if names is None:
        return code or "?"
    return names.get(in_lang) or names.get(DEFAULT_LANG) or code


def entity_type_label(etype: str, lang: str = DEFAULT_LANG) -> str:
    """Etichetta leggibile del TIPO entità (persona|progetto|termine) nella lingua app. Lo schema
    mantiene i valori enum italiani (contratto JSON); qui si traduce solo la visualizzazione.
    Tipo fuori-enum → il valore grezzo (tollerante)."""
    key = f"entity.{etype}"
    return t(key, lang) if key in _CATALOG else (etype or "")


def model_desc(name: str, lang: str = DEFAULT_LANG) -> str:
    """Descrizione localizzata di un modello curato (card "Modelli AI"). Modello non in catalogo
    → "" (il chiamante usa il fallback off_desc)."""
    key = f"models.desc.{name}"
    return t(key, lang) if key in _CATALOG else ""


def model_tags(tags: list[str] | None, lang: str = DEFAULT_LANG) -> list[str]:
    """Traduce i tag del catalogo modelli; un tag senza traduzione resta grezzo (tollerante)."""
    out = []
    for tg in tags or []:
        key = f"models.tag.{tg}"
        out.append(t(key, lang) if key in _CATALOG else tg)
    return out
