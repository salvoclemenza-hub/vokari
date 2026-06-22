"""Orchestrazione GUI: trascrizione (streaming) -> analisi -> intervista -> briefing.
Emette eventi via il callback `emit(event, payload)`; l'Api li inoltra al JS con
evaluate_js. Riusa interamente il motore (M1-M4) e llm.factory (DRY)."""

import time
from datetime import date
from pathlib import Path

from app import debuglog
from app.jobs import Job, JobStore
from vokari import settings as settings_mod
from vokari.analyze import analyzer as analyzer_mod
from vokari.analyze import fit as fit_mod
from vokari.analyze import interview as interview_mod
from vokari.analyze.preview import preview_from_partial_json
from vokari.analyze.schema import Analysis, Meta
from vokari.audio import convert as convert_mod
from vokari.llm.factory import make_provider
from vokari.render import briefing as briefing_mod
from vokari.render import obsidian as obsidian_mod
from vokari.render import recap as recap_mod
from vokari.transcribe import whisper as whisper_mod

# Throttle per gli emit di anteprima: ~120ms per ridurre flood evaluate_js
_PREVIEW_THROTTLE_S = 0.12

# P5: oltre ~30 min, large-v3 (non turbo) su CPU diventa molto lento (~3x turbo) → si suggerisce
# large-v3-turbo. Metà del tempo perso nel caso ECO 5.0 era proprio large-v3 su 2h11m.
_LONG_AUDIO_S = 1800


def _is_slow_large_model(model: str) -> bool:
    m = (model or "").lower()
    return "large" in m and "turbo" not in m


def _throttle(interval_s: float):
    """Decoratore: esegue la funzione solo se sono passati >= interval_s secondi dall'ultima esecuzione."""

    def decorator(fn):
        state = {"last_call": 0}

        def wrapper(*args, **kwargs):
            now = time.monotonic()
            if now - state["last_call"] >= interval_s:
                state["last_call"] = now
                return fn(*args, **kwargs)

        return wrapper

    return decorator


def _slug(text: str) -> str:
    keep = "".join(c if c.isalnum() or c in " -_" else "" for c in text).strip()
    return ("-".join(keep.split()) or "sessione").lower()[:60]


def _llm_label(s) -> str:
    return ("ollama:" + s.ollama_model) if s.brain == "ollama" else s.claude_model


def _briefing_out_path(s, job: Job) -> Path:
    name = f"{_slug(job.title)}.briefing.md"
    if s.briefing_dir:
        d = Path(s.briefing_dir)
        d.mkdir(parents=True, exist_ok=True)
        return d / name
    if job.audio_path:
        return Path(job.audio_path).with_suffix(".briefing.md")
    # audio_path vuoto (import senza file, test headless): fallback a userData/data/briefings/
    from vokari.paths import ensure_dirs

    d = ensure_dirs().data / "briefings"
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def run_processing(job: Job, store: JobStore, *, settings=None, provider=None, emit=None) -> Job:
    s = settings or settings_mod.load()

    def _emit(ev: str, payload: dict) -> None:
        if emit:
            emit(ev, payload)

    if store.get(job.id).status == "cancelled":
        _emit("status", {"jobId": job.id, "status": "cancelled"})
        return store.get(job.id)

    try:
        # Pre-flight Ollama: se il brain è Ollama e il server è giù, proviamo ad avviarlo
        # PRIMA di trascrivere — così un audio da 1h non viene processato per poi fallire
        # all'analisi. provider iniettato (test) ⇒ salta il check. Vedi ADR Ollama auto-fix.
        if provider is None and s.brain == "ollama":
            from vokari.llm import ollama_provider as ollama_mod

            _already_up = ollama_mod.is_up(s.ollama_endpoint)
            if not _already_up:
                _emit("warning", {"messages": ["Ollama non era attivo: avvio automatico in corso…"]})
                if not ollama_mod.ensure_available(s.ollama_endpoint):
                    msg = (
                        "Ollama non è raggiungibile e non è stato possibile avviarlo "
                        "automaticamente. Avvialo manualmente o passa a Claude nelle Impostazioni."
                    )
                    store.update(job.id, status="error", error=msg)
                    _emit("status", {"jobId": job.id, "status": "error", "error": msg})
                    return store.get(job.id)
            _emit("warning", {"messages": []})  # pulisce il banner: Ollama è attivo (già su / appena riavviato)

        # Provider creato PRIMA della trascrizione (fail-fast, come il pre-flight Ollama: meglio
        # fallire subito su key Claude mancante che dopo un'ora di trascrizione). Riusato da A1/A2.
        prov = provider or make_provider(s)

        # Preflight (piano timeout-robustezza A1 + P5): se la durata audio è nota PRIMA di
        # trascrivere, avvisa subito — il caso ECO 5.0 ha trascritto 2h18m per poi scoprire che
        # con qwen la trascrizione andava riassunta. probe_duration_s è best-effort (ffprobe).
        preflight_warned = False
        dur_pre = convert_mod.probe_duration_s(job.audio_path)
        if dur_pre and dur_pre > _LONG_AUDIO_S and _is_slow_large_model(job.model):
            _emit(
                "warning",
                {
                    "messages": [
                        f"Registrazione lunga (~{round(dur_pre / 60)} min) con «{job.model}»: "
                        "large-v3-turbo è circa 3x più veloce a parità di qualità pratica "
                        "(puoi cambiarlo in Modelli AI)."
                    ]
                },
            )
        if dur_pre:
            try:
                pre = fit_mod.estimate_from_duration(dur_pre, prov)
                if pre.level != "ideal":
                    _emit(
                        "analysis_fit",
                        {
                            "jobId": job.id,
                            "level": pre.level,
                            "tokensEst": pre.tokens_est,
                            "ctxMax": pre.ctx_max,
                            "budget": pre.budget,
                            "nChunks": pre.n_chunks,
                            "ctxIsFallback": pre.ctx_is_fallback,
                            "recommendation": pre.recommendation,
                        },
                    )
                    _emit("warning", {"messages": [f"{pre.reason} {pre.recommendation}".strip()]})
                    preflight_warned = True
            except Exception as e:  # diagnostica, mai fatale per la trascrizione
                debuglog.log_exc("analysis_fit_preflight_failed", e, jobId=job.id)

        store.update(job.id, status="transcribing", pct=0.0)
        _emit("status", {"jobId": job.id, "status": "transcribing"})

        def on_seg(pct: float, text_so_far: str, seg_text: str, from_cache: bool = False) -> None:
            store.update(job.id, pct=pct, partial_text=text_so_far)
            # CONTRATTO: `text` è il testo CUMULATIVO (text_so_far), NON il segmento corrente.
            # Il frontend (App.tsx, Processing.tsx) tratta payload.text come cumulativo e lo usa
            # come prefisso del typewriter; emettere il solo segmento faceva lampeggiare/azzerare
            # la console a ogni frase. Coerente con partial_text salvato nello store (resume).
            # NB: dict letterale inline (non variabile) → il backbone test_contract.py lo verifica via regex.
            _emit("transcribe_progress", {"jobId": job.id, "pct": pct, "text": text_so_far, "fromCache": from_cache})

        def _cancelled() -> bool:
            return store.get(job.id).status == "cancelled"

        result = whisper_mod.transcribe_stream(
            job.audio_path, model=job.model, language=job.language, on_segment=on_seg, should_cancel=_cancelled
        )

        if _cancelled() or result.get("cancelled"):
            _emit("status", {"jobId": job.id, "status": "cancelled"})
            return store.get(job.id)

        # Audio senza parlato / registrazione di 0s → trascrizione vuota: fermati con un
        # messaggio chiaro invece di generare un briefing vuoto pieno di placeholder (E1).
        if not result["text"].strip():
            msg = "Trascrizione vuota: nessun parlato rilevato nell'audio."
            store.update(job.id, transcript="", duration_s=result["duration_s"], status="error", error=msg)
            _emit("status", {"jobId": job.id, "status": "error", "error": msg})
            return store.get(job.id)

        store.update(job.id, transcript=result["text"], duration_s=result["duration_s"], pct=1.0, status="analyzing")
        _emit("status", {"jobId": job.id, "status": "analyzing"})

        # A2 (check idoneità, piano timeout-robustezza): conferma con i NUMERI REALI della
        # trascrizione se è adatta al contesto del modello, PRIMA di spendere l'analisi. Tollerante:
        # un errore qui non blocca l'analisi. `fit_report` è riusato da P2 per decidere il testo
        # passato a detect_questions. Il warning leggibile NON si ripete se A1 ha già avvisato.
        fit_report = None
        try:
            report = fit_mod.assess_fit(result["text"], prov)
            fit_report = report
            if report.level != "ideal":
                _emit(
                    "analysis_fit",
                    {
                        "jobId": job.id,
                        "level": report.level,
                        "tokensEst": report.tokens_est,
                        "ctxMax": report.ctx_max,
                        "budget": report.budget,
                        "nChunks": report.n_chunks,
                        "ctxIsFallback": report.ctx_is_fallback,
                        "recommendation": report.recommendation,
                    },
                )
                if not preflight_warned:
                    _emit("warning", {"messages": [f"{report.reason} {report.recommendation}".strip()]})
        except Exception as e:  # diagnostica, mai fatale per l'analisi
            debuglog.log_exc("analysis_fit_failed", e, jobId=job.id)

        # Callback per lo streaming dell'anteprima: riceve il JSON grezzo accumulato, estrae
        # i valori leggibili, e li emette throttled al frontend (evita flood evaluate_js).
        # on_progress è None se il provider non ha chat_json_stream, così l'analyzer fa fallback
        # a chat_json normalmente. La preview NON viene mostrata durante la trascrizione (evento
        # analysis_preview ha un id job diverso dalla live_transcript) → niente confusione.
        @_throttle(_PREVIEW_THROTTLE_S)
        def _emit_analysis_preview(raw_json: str) -> None:
            _emit(
                "analysis_preview",
                {"jobId": job.id, "text": preview_from_partial_json(raw_json)},
            )

        def _emit_analyze_step(step: str) -> None:
            # Emette substep della fase analyzing (es. "verify", "questions") per il timer/label
            # nella schermata Processing. Il backend non chiama this per ogni step opzionale
            # (es. se verify=False), ma solo quando il step davvero sta per eseguirsi.
            step_labels = {
                "verify": "Ricontrollo di aver colto tutto",
                "questions": "Preparo le domande di rifinitura",
            }
            label = step_labels.get(step, step)
            _emit("analyze_step", {"jobId": job.id, "step": step, "label": label})

        # verify=True attiva il check di copertura "ho colto il punto?" (Task 8); l'analyzer lo
        # esegue solo se serve (purpose debole o mode=riunione) per non raddoppiare i tempi su CPU.
        analysis = analyzer_mod.analyze(
            result["text"],
            mode=job.mode,
            context=job.context or None,
            verify=True,
            provider=prov,
            emit=_emit,
            should_cancel=_cancelled,
            on_progress=_emit_analysis_preview,
            on_step=_emit_analyze_step,
        )
        # P1 (anti-perdita, piano timeout-robustezza): persisti l'analisi — il risultato COSTOSO
        # (minuti su CPU) — PRIMA di detect_questions. detect_questions è uno step OPZIONALE (0
        # domande ⇒ niente intervista, il briefing si genera comunque) ma il suo fallimento (es.
        # read-timeout di Ollama su modello lento) non deve mai far perdere ore di lavoro pronto.
        store.update(job.id, analysis=analysis.model_dump())

        # P2 (anti-timeout): NON re-inviare il transcript INTEGRALE a detect_questions — era la
        # chiamata più pesante di tutte (re-incollava ~98k char IGNORANDO il riassunto già fatto
        # dall'analyzer → read-timeout sull'ultimo step). L'analisi JSON è già un riassunto
        # strutturato: passiamo il transcript SOLO se è ideale per il modello, altrimenti "".
        q_transcript = result["text"] if (fit_report is None or fit_report.level == "ideal") else ""

        _emit_analyze_step("questions")
        try:
            questions = interview_mod.detect_questions(
                analysis, q_transcript, provider=prov, mode=job.mode, should_cancel=_cancelled
            )
        except Exception as e:
            # Domande non producibili (modello lento/timeout, ma anche questions malformate dall'LLM):
            # NON è fatale. Catch volutamente AMPIO (anti-perdita: lo step domande è opzionale, non
            # deve mai far perdere ore di analisi) ma SEMPRE loggato → un eventuale bug vero resta
            # visibile nel debug log. Salta l'intervista e genera il briefing (ramo `if not questions`).
            debuglog.log_exc("detect_questions_failed", e, jobId=job.id)
            _emit(
                "warning",
                {
                    "messages": [
                        "Non sono riuscito a preparare le domande di rifinitura (il modello è "
                        "lento): salto l'intervista e genero comunque il briefing."
                    ]
                },
            )
            questions = []
        # Annulla durante analisi/intervista (chiamate LLM lunghe, sync, non interrompibili):
        # se nel frattempo lo status è diventato 'cancelled', fermati QUI. Senza questo check
        # gli update successivi (questions/awaiting_interview) clobbererebbero la cancellazione
        # e la sessione verrebbe salvata pur essendo stata annullata dall'utente.
        if _cancelled():
            _emit("status", {"jobId": job.id, "status": "cancelled"})
            return store.get(job.id)
        store.update(job.id, questions=[q.model_dump() for q in questions])

        # 0 domande → niente schermata intervista: genera subito il briefing (→ ready).
        # answers/skipped vuoti ⇒ build_refinement vuoto (niente ri-analisi) e nessun marcatore.
        if not questions:
            try:
                return generate_briefing(store.get(job.id), store, {}, [], settings=s, provider=prov, emit=emit)
            except Exception as e:
                debuglog.log_exc("pipeline_error", e, jobId=job.id, phase="generate_briefing")
                store.update(job.id, status="error", error=str(e))
                _emit("status", {"jobId": job.id, "status": "error", "error": str(e)})
                return store.get(job.id)

        store.update(job.id, status="awaiting_interview")
        _emit("status", {"jobId": job.id, "status": "awaiting_interview"})
        return store.get(job.id)
    except Exception as e:
        debuglog.log_exc("pipeline_error", e, jobId=job.id, phase="run_processing")
        store.update(job.id, status="error", error=str(e))
        _emit("status", {"jobId": job.id, "status": "error", "error": str(e)})
        raise


def generate_briefing(
    job: Job, store: JobStore, answers: dict, skipped: list, *, settings=None, provider=None, emit=None
) -> Job:
    s = settings or settings_mod.load()

    def _emit(ev: str, payload: dict) -> None:
        if emit:
            emit(ev, payload)

    if store.get(job.id).status == "cancelled":
        _emit("status", {"jobId": job.id, "status": "cancelled"})
        return store.get(job.id)

    questions = [interview_mod.Question.model_validate(q) for q in job.questions]
    refinement = interview_mod.build_refinement(questions, answers, skipped)
    markers = interview_mod.da_chiarire_markers(questions, answers, skipped)

    analysis = Analysis.model_validate(job.analysis) if job.analysis else Analysis(meta=Meta())
    if refinement:
        store.update(job.id, status="analyzing")
        _emit("status", {"jobId": job.id, "status": "analyzing"})
        prov = provider or make_provider(s)

        # Reusa i callback di anteprima e substep come in run_processing per coerenza
        # (il refinement è una ri-analisi con le risposte all'intervista).
        @_throttle(_PREVIEW_THROTTLE_S)
        def _emit_analysis_preview_refinement(raw_json: str) -> None:
            _emit(
                "analysis_preview",
                {"jobId": job.id, "text": preview_from_partial_json(raw_json)},
            )

        def _emit_analyze_step_refinement(step: str) -> None:
            step_labels = {
                "verify": "Ricontrollo di aver colto tutto",
                "questions": "Preparo le domande di rifinitura",
            }
            label = step_labels.get(step, step)
            _emit("analyze_step", {"jobId": job.id, "step": step, "label": label})

        analysis = analyzer_mod.analyze(
            job.transcript,
            mode=job.mode,
            context=job.context or None,
            provider=prov,
            refinement=refinement,
            on_progress=_emit_analysis_preview_refinement,
            on_step=_emit_analyze_step_refinement,
        )

    # Annulla durante il refinement (chiamata LLM lunga): non scrivere il briefing né
    # passare a 'ready' se l'utente ha annullato nel frattempo.
    if store.get(job.id).status == "cancelled":
        _emit("status", {"jobId": job.id, "status": "cancelled"})
        return store.get(job.id)

    # Meta strutturali deterministici: il modello le sbaglia/lascia vuote.
    analysis.meta.type = "meeting" if job.mode == "riunione" else "solo"
    if job.duration_s:
        analysis.meta.duration_min = max(1, round(job.duration_s / 60))
    if not analysis.meta.date:
        analysis.meta.date = date.today().isoformat()
    if not analysis.meta.title:
        analysis.meta.title = job.title

    store.update(job.id, status="rendering")
    _emit("status", {"jobId": job.id, "status": "rendering"})
    md = briefing_mod.render_briefing(
        analysis,
        source=Path(job.audio_path).name,
        transcription_model=job.model,
        llm_model=_llm_label(s),
        session_id=job.id,
        transcript=job.transcript,
        da_chiarire=markers,
        language=("" if job.language in ("", "auto") else job.language),
        word_count=len(job.transcript.split()),
    )
    out_path = _briefing_out_path(s, job)
    out_path.write_text(md, encoding="utf-8")

    # Artefatti aggiuntivi (stesso JSON, nessuna chiamata LLM extra). I marcatori [DA CHIARIRE]
    # vanno a TUTTI gli output (briefing, recap, nota Obsidian), non solo al briefing.
    recap_md = recap_mod.render_recap(analysis, title=job.title, da_chiarire=markers)
    notes = obsidian_mod.render_obsidian_notes(
        analysis, session_title=job.title, session_date=analysis.meta.date, da_chiarire=markers
    )
    obsidian_note = notes[0].content if notes else ""

    job = store.update(
        job.id,
        briefing_md=md,
        briefing_path=str(out_path),
        recap_md=recap_md,
        obsidian_note=obsidian_note,
        da_chiarire=markers,  # persistito: l'export Obsidian re-renderizza completo dei marcatori
        status="ready",
    )
    _emit("status", {"jobId": job.id, "status": "ready"})
    return job
