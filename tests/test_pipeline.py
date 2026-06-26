import pytest
from app import pipeline as P
from app.jobs import Job, JobStore

from vokari.analyze import interview as IV
from vokari.analyze.schema import Analysis, Meta
from vokari.settings import Settings


class StubProvider:
    def chat_json(self, system, user):
        return {}

    def chat_text(self, system, user):
        return ""


@pytest.fixture
def store(tmp_path):
    return JobStore(jobs_dir=tmp_path / "jobs")


def _patch_engine(monkeypatch, analysis, questions):
    monkeypatch.setattr(P.models_mod, "is_downloaded", lambda name: True)

    def fake_stream(path, *, model, language, on_segment=None, should_cancel=None):
        if on_segment:
            on_segment(1.0, "testo trascritto", "testo trascritto")
        return {"text": "testo trascritto", "duration_s": 12.0}

    monkeypatch.setattr(P.whisper_mod, "transcribe_stream", fake_stream)
    monkeypatch.setattr(P.analyzer_mod, "analyze", lambda text, *, mode, provider, refinement=None, **_kw: analysis)
    monkeypatch.setattr(
        P.interview_mod, "detect_questions", lambda a, t, *, provider, mode, should_cancel=None, **_kw: questions
    )


def test_run_processing_drives_status_and_emits(store, monkeypatch):
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    qs = [IV.Question(id="q1", text="Budget?", priority="high")]
    _patch_engine(monkeypatch, analysis, qs)
    job = store.create(Job.new("/tmp/a.wav", model="small", language="it", mode="solo"))

    events: list[tuple[str, dict]] = []
    out = P.run_processing(
        job, store, settings=Settings(), provider=StubProvider(), emit=lambda ev, payload: events.append((ev, payload))
    )

    assert out.status == "awaiting_interview"
    assert out.transcript == "testo trascritto"
    assert out.questions and out.questions[0]["id"] == "q1"
    names = [ev for ev, _ in events]
    assert "transcribe_progress" in names and "status" in names


def test_transcribe_progress_emits_cumulative_text(store, tmp_path, monkeypatch):
    """CONTRATTO: l'evento transcribe_progress.text è CUMULATIVO (text_so_far), non il
    segmento corrente. Regressione: prima emetteva seg_text → la console frontend lampeggiava."""
    analysis = Analysis(meta=Meta(type="solo", title="X"))

    def fake_stream(path, *, model, language, on_segment=None, should_cancel=None):
        if on_segment:
            on_segment(0.5, "ciao", "ciao")  # text_so_far, seg_text
            on_segment(1.0, "ciao mondo", " mondo")  # cumulativo cresce, seg diverso
        return {"text": "ciao mondo", "duration_s": 5.0}

    monkeypatch.setattr(P.models_mod, "is_downloaded", lambda name: True)
    monkeypatch.setattr(P.whisper_mod, "transcribe_stream", fake_stream)
    monkeypatch.setattr(P.analyzer_mod, "analyze", lambda text, *, mode, provider, refinement=None, **_kw: analysis)
    monkeypatch.setattr(P.interview_mod, "detect_questions", lambda a, t, *, provider, mode, **_kw: [])
    job = store.create(Job.new("/tmp/a.wav", model="small", language="it", mode="solo"))

    events: list[tuple[str, dict]] = []
    P.run_processing(
        job,
        store,
        settings=Settings(briefing_dir=str(tmp_path / "out")),
        provider=StubProvider(),
        emit=lambda ev, payload: events.append((ev, payload)),
    )

    texts = [p["text"] for ev, p in events if ev == "transcribe_progress"]
    assert texts == ["ciao", "ciao mondo"]  # cumulativo, NON [" mondo"]
    # ogni testo è prefisso del successivo (invariante che il typewriter frontend assume)
    assert texts[1].startswith(texts[0])


def test_run_processing_no_questions_generates_briefing_directly(store, tmp_path, monkeypatch):
    """0 domande → niente schermata intervista: si genera subito il briefing → ready."""
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    _patch_engine(monkeypatch, analysis, [])  # detect_questions ritorna lista vuota
    job = store.create(Job.new(str(tmp_path / "a.wav"), model="small", language="it", mode="solo"))

    events: list[tuple[str, dict]] = []
    s = Settings(briefing_dir=str(tmp_path / "out"))
    out = P.run_processing(
        job, store, settings=s, provider=StubProvider(), emit=lambda ev, payload: events.append((ev, payload))
    )

    assert out.status == "ready"
    assert out.briefing_md  # briefing generato
    assert out.briefing_path
    # nessun evento awaiting_interview emesso
    statuses = [p.get("status") for ev, p in events if ev == "status"]
    assert "awaiting_interview" not in statuses
    assert "ready" in statuses
    # niente marcatori DA CHIARIRE (answers/skipped vuoti)
    assert "DA CHIARIRE" not in out.briefing_md


def test_run_processing_detect_questions_failure_still_generates_briefing(store, tmp_path, monkeypatch):
    """P1 (anti-perdita): se detect_questions fallisce (es. read-timeout di Ollama su modello
    lento), l'analisi — il lavoro COSTOSO — NON va persa: il job arriva a 'ready' col briefing,
    l'analisi è persistita e viene emesso un `warning` (NON `status=error`). Seam reale (no mock
    della pipeline): solo whisper/analyze finti, detect_questions che solleva davvero."""
    from vokari.llm.base import LLMError

    analysis = Analysis(meta=Meta(type="solo", title="X"))

    def fake_stream(path, *, model, language, on_segment=None, should_cancel=None):
        return {"text": "testo reale trascritto", "duration_s": 10.0}

    def boom(a, t, *, provider, mode, should_cancel=None):
        raise LLMError("Ollama è attivo ma la risposta ha superato il timeout")

    monkeypatch.setattr(P.models_mod, "is_downloaded", lambda name: True)
    monkeypatch.setattr(P.whisper_mod, "transcribe_stream", fake_stream)
    monkeypatch.setattr(P.analyzer_mod, "analyze", lambda text, *, mode, provider, refinement=None, **_kw: analysis)
    monkeypatch.setattr(P.interview_mod, "detect_questions", boom)
    job = store.create(Job.new(str(tmp_path / "a.wav"), model="small", language="it", mode="solo"))

    events: list[tuple[str, dict]] = []
    s = Settings(briefing_dir=str(tmp_path / "out"))
    out = P.run_processing(job, store, settings=s, provider=StubProvider(), emit=lambda ev, p: events.append((ev, p)))

    assert out.status == "ready", "il fallimento delle domande NON deve dare status=error"
    assert out.briefing_md and out.briefing_path  # briefing generato malgrado il timeout domande
    assert out.analysis, "l'analisi deve essere persistita PRIMA di detect_questions (anti-perdita)"
    statuses = [p.get("status") for ev, p in events if ev == "status"]
    assert "error" not in statuses and "ready" in statuses
    assert any(ev == "warning" for ev, _ in events), "deve avvisare che salta l'intervista"


def test_run_processing_emits_analysis_fit_when_transcript_exceeds_budget(store, tmp_path, monkeypatch):
    """A2 (check idoneità): se la trascrizione reale supera il budget del modello, la pipeline
    emette analysis_fit (numeri reali) + warning PRIMA dell'analisi. Seam reale: solo whisper e
    analyze finti, fit.assess_fit gira davvero sul provider con budget piccolo."""
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    long_text = " ".join(["parola"] * 4000)

    def fake_stream(path, *, model, language, on_segment=None, should_cancel=None):
        return {"text": long_text, "duration_s": 600.0}

    monkeypatch.setattr(P.whisper_mod, "transcribe_stream", fake_stream)
    monkeypatch.setattr(P.analyzer_mod, "analyze", lambda text, *, mode, provider, refinement=None, **_kw: analysis)
    monkeypatch.setattr(
        P.interview_mod, "detect_questions", lambda a, t, *, provider, mode, should_cancel=None, **_kw: []
    )

    class _BudgetProv:
        def chat_json(self, system, user):
            return {}

        def chat_text(self, system, user):
            return ""

        def context_budget_tokens(self):
            return 100  # budget minuscolo → la trascrizione lo supera

        def model_max_ctx(self):
            return 8192

    job = store.create(Job.new(str(tmp_path / "a.wav"), model="small", language="it", mode="solo"))
    events: list[tuple[str, dict]] = []
    P.run_processing(
        job,
        store,
        settings=Settings(briefing_dir=str(tmp_path / "out")),
        provider=_BudgetProv(),
        emit=lambda ev, p: events.append((ev, p)),
    )

    fits = [p for ev, p in events if ev == "analysis_fit"]
    assert fits, "analysis_fit non emesso pur superando il budget del modello"
    assert fits[0]["level"] in ("summarize", "over_even_summarized")
    assert fits[0]["jobId"] == job.id
    assert "tokensEst" in fits[0] and fits[0]["recommendation"]


def test_run_processing_no_analysis_fit_for_stub_provider(store, tmp_path, monkeypatch):
    """Anti-regressione: un provider senza budget noto (stub/fake) NON deve emettere analysis_fit
    (level ideal) → i test esistenti della pipeline restano verdi e l'evento non è rumoroso."""
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    _patch_engine(monkeypatch, analysis, [])
    job = store.create(Job.new(str(tmp_path / "a.wav"), model="small", language="it", mode="solo"))
    events: list[tuple[str, dict]] = []
    P.run_processing(
        job,
        store,
        settings=Settings(briefing_dir=str(tmp_path / "out")),
        provider=StubProvider(),
        emit=lambda ev, p: events.append((ev, p)),
    )
    assert not [p for ev, p in events if ev == "analysis_fit"]


def test_detect_questions_gets_empty_transcript_when_over_budget(store, tmp_path, monkeypatch):
    """P2 (anti-timeout): quando la trascrizione non è ideale per il modello, detect_questions
    NON riceve il transcript integrale (era la chiamata più pesante → read-timeout): riceve ""
    e lavora sull'analisi JSON già riassunta."""
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    long_text = " ".join(["parola"] * 4000)
    captured: dict = {}

    def fake_stream(path, *, model, language, on_segment=None, should_cancel=None):
        return {"text": long_text, "duration_s": 600.0}

    def fake_detect(a, t, *, provider, mode, should_cancel=None, **_kw):
        captured["t"] = t
        return []

    monkeypatch.setattr(P.whisper_mod, "transcribe_stream", fake_stream)
    monkeypatch.setattr(P.analyzer_mod, "analyze", lambda text, *, mode, provider, refinement=None, **_kw: analysis)
    monkeypatch.setattr(P.interview_mod, "detect_questions", fake_detect)

    class _BudgetProv:
        def chat_json(self, system, user):
            return {}

        def chat_text(self, system, user):
            return ""

        def context_budget_tokens(self):
            return 100

        def model_max_ctx(self):
            return 8192

    job = store.create(Job.new(str(tmp_path / "a.wav"), model="small", language="it", mode="solo"))
    P.run_processing(
        job, store, settings=Settings(briefing_dir=str(tmp_path / "out")), provider=_BudgetProv(), emit=None
    )
    assert captured["t"] == "", "detect_questions deve ricevere transcript vuoto quando supera il budget"


def test_detect_questions_gets_full_transcript_when_ideal(store, tmp_path, monkeypatch):
    """Contraltare di P2: trascrizione ideale (o provider senza budget noto) → detect_questions
    riceve il transcript intero (comportamento invariato)."""
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    captured: dict = {}

    def fake_stream(path, *, model, language, on_segment=None, should_cancel=None):
        return {"text": "trascrizione breve", "duration_s": 12.0}

    def fake_detect(a, t, *, provider, mode, should_cancel=None, **_kw):
        captured["t"] = t
        return []

    monkeypatch.setattr(P.whisper_mod, "transcribe_stream", fake_stream)
    monkeypatch.setattr(P.analyzer_mod, "analyze", lambda text, *, mode, provider, refinement=None, **_kw: analysis)
    monkeypatch.setattr(P.interview_mod, "detect_questions", fake_detect)
    job = store.create(Job.new(str(tmp_path / "a.wav"), model="small", language="it", mode="solo"))
    P.run_processing(
        job, store, settings=Settings(briefing_dir=str(tmp_path / "out")), provider=StubProvider(), emit=None
    )
    assert captured["t"] == "trascrizione breve"


def test_run_processing_preflight_suggests_turbo_for_long_large_v3(store, tmp_path, monkeypatch):
    """P5: audio lungo (>30min) trascritto con large-v3 (non turbo) → warning che suggerisce
    large-v3-turbo PRIMA di iniziare la trascrizione lenta."""
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    _patch_engine(monkeypatch, analysis, [])
    monkeypatch.setattr(P.convert_mod, "probe_duration_s", lambda path: 3600.0)  # 1h

    job = store.create(Job.new(str(tmp_path / "a.wav"), model="large-v3", language="it", mode="solo"))
    events: list[tuple[str, dict]] = []
    P.run_processing(
        job,
        store,
        settings=Settings(briefing_dir=str(tmp_path / "out")),
        provider=StubProvider(),
        emit=lambda ev, p: events.append((ev, p)),
    )
    warns = [m for ev, p in events if ev == "warning" for m in p.get("messages", [])]
    assert any("turbo" in m.lower() for m in warns), "deve suggerire large-v3-turbo per audio lungo"


def test_run_processing_preflight_no_turbo_hint_for_turbo_model(store, tmp_path, monkeypatch):
    """Anti-rumore: se il modello è già large-v3-turbo, nessun suggerimento turbo."""
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    _patch_engine(monkeypatch, analysis, [])
    monkeypatch.setattr(P.convert_mod, "probe_duration_s", lambda path: 3600.0)

    job = store.create(Job.new(str(tmp_path / "a.wav"), model="large-v3-turbo", language="it", mode="solo"))
    events: list[tuple[str, dict]] = []
    P.run_processing(
        job,
        store,
        settings=Settings(briefing_dir=str(tmp_path / "out")),
        provider=StubProvider(),
        emit=lambda ev, p: events.append((ev, p)),
    )
    warns = [m for ev, p in events if ev == "warning" for m in p.get("messages", [])]
    assert not any("turbo" in m.lower() for m in warns)


def test_run_processing_preflight_emits_analysis_fit_from_duration(store, tmp_path, monkeypatch):
    """A1 (preflight): con durata nota e modello dal contesto piccolo, la pipeline emette
    analysis_fit STIMATO prima di trascrivere (evita il caso ECO 5.0: 2h18m sprecate)."""
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    _patch_engine(monkeypatch, analysis, [])
    monkeypatch.setattr(P.convert_mod, "probe_duration_s", lambda path: 7840.0)  # ~2h11m

    class _BudgetProv(StubProvider):
        def context_budget_tokens(self):
            return 30000

        def model_max_ctx(self):
            return 32768

    job = store.create(Job.new(str(tmp_path / "a.wav"), model="large-v3-turbo", language="it", mode="solo"))
    events: list[tuple[str, dict]] = []
    P.run_processing(
        job,
        store,
        settings=Settings(briefing_dir=str(tmp_path / "out")),
        provider=_BudgetProv(),
        emit=lambda ev, p: events.append((ev, p)),
    )
    fits = [p for ev, p in events if ev == "analysis_fit"]
    assert fits, "A1 deve emettere analysis_fit stimato dalla durata"
    assert fits[0]["level"] in ("summarize", "over_even_summarized")


def test_run_processing_empty_transcript_errors(store, tmp_path, monkeypatch):
    """Audio senza parlato → trascrizione vuota: job in error con messaggio chiaro,
    niente briefing vuoto. Analyze NON viene chiamato (E1)."""

    def fake_stream(path, *, model, language, on_segment=None, should_cancel=None):
        if on_segment:
            on_segment(1.0, "", "")
        return {"text": "   ", "duration_s": 3.0}  # solo whitespace

    analyze_called = {"v": False}

    def fake_analyze(text, *, mode, provider, refinement=None):
        analyze_called["v"] = True
        return Analysis(meta=Meta(type="solo"))

    monkeypatch.setattr(P.whisper_mod, "transcribe_stream", fake_stream)
    monkeypatch.setattr(P.analyzer_mod, "analyze", fake_analyze)
    job = store.create(Job.new(str(tmp_path / "a.wav"), model="small", language="it", mode="solo"))

    events: list[tuple[str, dict]] = []
    out = P.run_processing(
        job, store, settings=Settings(), provider=StubProvider(), emit=lambda ev, payload: events.append((ev, payload))
    )

    assert out.status == "error"
    assert "vuota" in out.error.lower()
    assert analyze_called["v"] is False
    statuses = [p.get("status") for ev, p in events if ev == "status"]
    assert "error" in statuses


def test_run_processing_with_questions_awaits_interview(store, tmp_path, monkeypatch):
    """≥1 domanda → comportamento invariato: awaiting_interview, briefing non ancora generato."""
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    qs = [IV.Question(id="q1", text="Budget?", priority="high")]
    _patch_engine(monkeypatch, analysis, qs)
    job = store.create(Job.new(str(tmp_path / "a.wav"), model="small", language="it", mode="solo"))

    events: list[tuple[str, dict]] = []
    out = P.run_processing(
        job, store, settings=Settings(), provider=StubProvider(), emit=lambda ev, payload: events.append((ev, payload))
    )

    assert out.status == "awaiting_interview"
    assert out.briefing_md == ""  # briefing NON ancora generato
    statuses = [p.get("status") for ev, p in events if ev == "status"]
    assert "awaiting_interview" in statuses
    assert "ready" not in statuses


def test_run_processing_aborts_when_cancelled_during_transcription(store, monkeypatch):
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    job = store.create(Job.new("/tmp/a.wav", model="small", language="it", mode="solo"))

    def fake_stream(path, *, model, language, on_segment=None, should_cancel=None):
        store.update(job.id, status="cancelled")  # arriva una cancellazione durante la trascrizione
        if on_segment:
            on_segment(1.0, "t", "t")
        return {"text": "t", "duration_s": 1.0}

    analyze_called = {"v": False}

    def fake_analyze(text, *, mode, provider, refinement=None):
        analyze_called["v"] = True
        return analysis

    monkeypatch.setattr(P.whisper_mod, "transcribe_stream", fake_stream)
    monkeypatch.setattr(P.analyzer_mod, "analyze", fake_analyze)

    out = P.run_processing(job, store, settings=Settings(), provider=StubProvider(), emit=None)
    assert out.status == "cancelled"
    assert analyze_called["v"] is False  # non deve chiamare Claude dopo la cancellazione


def test_run_processing_aborts_when_cancelled_during_analysis(store, monkeypatch):
    """Annulla durante l'analisi (chiamata LLM lunga): lo status 'cancelled' NON deve essere
    clobberato da awaiting_interview e la sessione non deve proseguire (cancel-ignored)."""
    job = store.create(Job.new("/tmp/a.wav", model="small", language="it", mode="solo"))

    def fake_stream(path, *, model, language, on_segment=None, should_cancel=None):
        return {"text": "testo reale trascritto", "duration_s": 10.0}

    def fake_analyze(text, *, mode, provider, refinement=None, **_kw):
        store.update(job.id, status="cancelled")  # l'utente annulla mentre l'LLM lavora
        return Analysis(meta=Meta(type="solo", title="X"))

    monkeypatch.setattr(P.whisper_mod, "transcribe_stream", fake_stream)
    monkeypatch.setattr(P.analyzer_mod, "analyze", fake_analyze)
    monkeypatch.setattr(
        P.interview_mod,
        "detect_questions",
        lambda a, t, *, provider, mode, should_cancel=None, **_kw: [IV.Question(id="q1", text="?", priority="high")],
    )

    events: list[tuple[str, dict]] = []
    out = P.run_processing(
        job, store, settings=Settings(), provider=StubProvider(), emit=lambda ev, p: events.append((ev, p))
    )

    assert out.status == "cancelled"
    statuses = [p.get("status") for ev, p in events if ev == "status"]
    assert "awaiting_interview" not in statuses  # non clobberato
    assert "cancelled" in statuses


def test_generate_briefing_aborts_when_cancelled_during_refinement(store, tmp_path, monkeypatch):
    """Annulla durante il refinement: niente file briefing, niente 'ready'."""
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    qs = [IV.Question(id="q1", text="Budget?")]
    job = store.create(Job.new(str(tmp_path / "a.wav"), model="small", mode="solo"))
    store.update(
        job.id,
        transcript="t",
        analysis=analysis.model_dump(),
        questions=[q.model_dump() for q in qs],
        status="awaiting_interview",
    )

    def fake_analyze(text, *, mode, context=None, provider, refinement=None, **kwargs):
        # **kwargs cattura on_progress, on_step, emit, should_cancel
        store.update(job.id, status="cancelled")
        return analysis

    monkeypatch.setattr(P.analyzer_mod, "analyze", fake_analyze)

    s = Settings(briefing_dir=str(tmp_path / "out"))
    out = P.generate_briefing(
        store.get(job.id), store, answers={"q1": "10k"}, skipped=[], settings=s, provider=StubProvider()
    )
    assert out.status == "cancelled"
    assert out.briefing_md == "" and out.briefing_path == ""


def test_generate_briefing_writes_file_with_markers(store, tmp_path, monkeypatch):
    analysis = Analysis(meta=Meta(type="solo", title="Sessione X"))
    qs = [IV.Question(id="q1", text="Budget?"), IV.Question(id="q2", text="Chi legge?")]
    monkeypatch.setattr(
        P.analyzer_mod, "analyze", lambda text, *, mode, context=None, provider, refinement=None, **kwargs: analysis
    )
    job = store.create(Job.new(str(tmp_path / "a.wav"), model="small", mode="solo"))
    store.update(
        job.id,
        transcript="t",
        analysis=analysis.model_dump(),
        questions=[q.model_dump() for q in qs],
        status="awaiting_interview",
    )

    s = Settings(briefing_dir=str(tmp_path / "out"))
    out = P.generate_briefing(
        store.get(job.id), store, answers={"q2": "il team"}, skipped=["q1"], settings=s, provider=StubProvider()
    )

    assert out.status == "ready"
    assert out.briefing_path and "DA CHIARIRE" in out.briefing_md
    assert "Budget? (domanda saltata in rifinitura)" in out.briefing_md


# ── Seam REALE dello streaming (ADR-010) ─────────────────────────────────────
# I contract-test guardano solo il SORGENTE via regex e i fake ignorano i callback:
# questi due test eseguono il motore VERO e verificano che gli eventi siano emessi davvero.


def test_analyzer_streams_progress_and_signals_verify():
    """Routing analyzer: con un provider che espone chat_json_stream + on_progress, l'analisi
    principale passa DAVVERO per lo streaming (on_progress riceve i delta) e segnala on_step
    ('verify') prima della verifica-copertura. Niente whisper: solo il motore analyze."""
    import json as _json

    from vokari.analyze import analyzer as A

    class _StreamProv:
        def chat_text(self, system, user):
            return ""

        def chat_json(self, system, user, *, json_schema=None):
            return {"meta": {"type": "meeting"}, "purpose": "Scopo verificato"}  # usato dalla verifica

        def chat_json_stream(self, system, user, *, json_schema=None, on_delta=None, should_cancel=None):
            full = '{"meta":{"type":"meeting"},"purpose":""}'  # purpose vuoto → coverage serve
            if on_delta:
                on_delta(full)
            return _json.loads(full)

    progress: list[str] = []
    steps: list[str] = []
    # mode=meeting → _coverage_needed sempre True → la verifica (e on_step) scattano
    A.analyze(
        "una trascrizione di riunione",
        mode="meeting",
        provider=_StreamProv(),
        verify=True,
        on_progress=progress.append,
        on_step=steps.append,
    )
    assert progress, "on_progress non invocato → lo streaming dell'analisi non è stato usato"
    assert "verify" in steps, "on_step('verify') non segnalato prima della verifica-copertura"


def test_run_processing_really_emits_analysis_preview_and_step(store, tmp_path, monkeypatch):
    """Seam end-to-end: con un provider streaming reale e SOLO whisper finto, la pipeline deve
    emettere analysis_preview (testo LEGGIBILE cumulativo, non JSON grezzo) e analyze_step.
    È il test che mancava (i contract-test ispezionano solo il sorgente)."""
    import json as _json

    # throttle a 0 così tutti i delta sintetici (sincroni) passano (in produzione ~120ms)
    monkeypatch.setattr(P, "_PREVIEW_THROTTLE_S", 0.0)

    def fake_stream(path, *, model, language, on_segment=None, should_cancel=None):
        if on_segment:
            on_segment(1.0, "testo", "testo")
        return {"text": "testo trascritto reale", "duration_s": 10.0}

    monkeypatch.setattr(P.whisper_mod, "transcribe_stream", fake_stream)

    _FULL = '{"meta":{"type":"solo"},"purpose":"Decidere la data di lancio","key_ideas":["ridurre i costi"]}'

    class _StreamProv:
        def chat_text(self, system, user):
            return ""

        def chat_json(self, system, user, *, json_schema=None):
            return {"questions": []}  # detect_questions → 0 domande

        def chat_json_stream(self, system, user, *, json_schema=None, on_delta=None, should_cancel=None):
            acc = ""
            for chunk in (_FULL[:25], _FULL[25:60], _FULL[60:]):
                acc += chunk
                if on_delta:
                    on_delta(acc)
            return _json.loads(_FULL)

    job = store.create(Job.new(str(tmp_path / "a.wav"), model="small", language="it", mode="solo"))
    events: list[tuple[str, dict]] = []
    P.run_processing(
        job,
        store,
        settings=Settings(briefing_dir=str(tmp_path / "out")),
        provider=_StreamProv(),
        emit=lambda ev, p: events.append((ev, p)),
    )

    previews = [p["text"] for ev, p in events if ev == "analysis_preview"]
    assert previews, "nessun evento analysis_preview emesso → seam streaming rotto"
    # l'anteprima finale è testo LEGGIBILE, non JSON grezzo
    assert "Decidere la data di lancio" in previews[-1]
    assert "{" not in previews[-1] and '"' not in previews[-1]
    # cumulativo: ogni anteprima è prefisso (o uguale) della successiva
    assert all(previews[i] == previews[i + 1][: len(previews[i])] for i in range(len(previews) - 1))
    steps = [p["step"] for ev, p in events if ev == "analyze_step"]
    assert "questions" in steps, "analyze_step('questions') non emesso prima di detect_questions"


def test_run_processing_downloads_model_when_missing(store, tmp_path, monkeypatch):
    """Preflight: modello non in cache → emette model_download start/done PRIMA di transcribing,
    e scarica via download_with_progress. Seam reale: solo models/whisper/analyze finti."""
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    _patch_engine(monkeypatch, analysis, [])
    # sovrascrivi lo stub di _patch_engine: questo modello NON è scaricato
    monkeypatch.setattr(P.models_mod, "is_downloaded", lambda name: False)
    monkeypatch.setattr(P.models_mod, "expected_bytes", lambda name: 1_600_000_000)
    called = {"download": False}

    def fake_dl(name, on_progress=None):
        called["download"] = True
        if on_progress:
            on_progress(800_000_000, 1_600_000_000)
        return "/fake/path"

    monkeypatch.setattr(P.models_mod, "download_with_progress", fake_dl)
    job = store.create(Job.new(str(tmp_path / "a.wav"), model="large-v3-turbo", language="it", mode="solo"))

    events: list[tuple[str, dict]] = []
    s = Settings(briefing_dir=str(tmp_path / "out"))
    out = P.run_processing(job, store, settings=s, provider=StubProvider(), emit=lambda ev, p: events.append((ev, p)))

    assert called["download"] is True
    dl = [p["status"] for ev, p in events if ev == "model_download"]
    assert "start" in dl and "done" in dl
    assert out.status == "ready"  # dopo il download, la pipeline prosegue normalmente


def test_run_processing_model_download_failure_is_terminal(store, tmp_path, monkeypatch):
    """Se il download del modello fallisce, il job va in error (no trascrizione a vuoto)."""
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    _patch_engine(monkeypatch, analysis, [])
    monkeypatch.setattr(P.models_mod, "is_downloaded", lambda name: False)
    monkeypatch.setattr(P.models_mod, "expected_bytes", lambda name: 0)
    monkeypatch.setattr(
        P.models_mod,
        "download_with_progress",
        lambda name, on_progress=None: (_ for _ in ()).throw(RuntimeError("rete assente")),
    )
    job = store.create(Job.new(str(tmp_path / "a.wav"), model="large-v3", language="it", mode="solo"))

    events: list[tuple[str, dict]] = []
    out = P.run_processing(
        job, store, settings=Settings(), provider=StubProvider(), emit=lambda ev, p: events.append((ev, p))
    )

    assert out.status == "error"
    assert "large-v3" in out.error
    err = [p for ev, p in events if ev == "model_download" and p.get("status") == "error"]
    assert err, "evento model_download error non emesso"


def test_run_processing_passes_markers_to_analyze(store, tmp_path, monkeypatch):
    """Seam reale: run_processing inoltra job.markers ad analyzer.analyze."""
    seen = {}
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    monkeypatch.setattr(P.models_mod, "is_downloaded", lambda name: True)

    def fake_stream(path, *, model, language, on_segment=None, should_cancel=None):
        return {"text": "testo trascritto", "duration_s": 5.0}

    monkeypatch.setattr(P.whisper_mod, "transcribe_stream", fake_stream)

    def fake_analyze(text, *, mode, provider, markers=None, **_kw):
        seen["markers"] = markers
        return analysis

    monkeypatch.setattr(P.analyzer_mod, "analyze", fake_analyze)
    monkeypatch.setattr(
        P.interview_mod, "detect_questions", lambda a, t, *, provider, mode, should_cancel=None, **_kw: []
    )
    job = store.create(
        Job.new(
            str(tmp_path / "a.wav"),
            model="small",
            language="it",
            mode="solo",
            markers=[{"t_ms": 5_000, "label": "Punto A"}],
        )
    )
    P.run_processing(
        job,
        store,
        settings=Settings(briefing_dir=str(tmp_path / "out")),
        provider=StubProvider(),
        emit=lambda ev, payload: None,
    )
    assert seen["markers"] == [{"t_ms": 5_000, "label": "Punto A"}]


def test_render_all_artifacts_renders_all_three_without_llm():
    """L02: render_all_artifacts produce briefing/recap/obsidian dai renderer REALI a
    partire da un Analysis già pronto, senza alcuna chiamata LLM/whisper."""
    analysis = Analysis(meta=Meta(type="meeting", title="Riunione", date="2026-06-23"))
    analysis.purpose = "Decidere se fare la landing page"
    analysis.key_ideas = ["Aggiungere il calendario stagionale"]

    out = P.render_all_artifacts(
        analysis,
        title="Riunione",
        source_name="rec.m4a",
        transcription_model="large-v3-turbo",
        llm_model="ollama:qwen2.5:7b",
        session_id="abc123",
        transcript="testo trascritto",
        da_chiarire=["Budget 700 o 730?"],
        markers=[{"t_ms": 1000, "label": "punto chiave"}],
        language="it",
        word_count=2,
    )
    assert "Decidere se fare la landing page" in out["briefing_md"]
    assert "session_id: abc123" in out["briefing_md"]
    assert "DA CHIARIRE: Budget 700 o 730?" in out["briefing_md"]
    assert out["recap_md"].startswith("# Recap — Riunione")
    assert "Budget 700 o 730?" in out["recap_md"]  # da_chiarire anche nel recap
    assert isinstance(out["obsidian_notes"], list) and len(out["obsidian_notes"]) >= 1
    assert out["obsidian_note"] == out["obsidian_notes"][0].content


def test_generate_briefing_warns_on_sparse_analysis(store, tmp_path):
    """L10: se l'analisi finale non ha contenuto strutturato (liste vuote), generate_briefing
    emette un warning leggibile MA genera comunque il briefing (status=ready, non bloccante)."""
    sparse = Analysis(meta=Meta(type="solo", title="Vuota"))  # purpose/liste vuoti → sparse
    job = store.create(Job.new(str(tmp_path / "a.wav"), model="small", mode="solo"))
    store.update(
        job.id,
        transcript="un po' di testo trascritto",
        analysis=sparse.model_dump(),
        questions=[],
        status="awaiting_interview",
    )
    events: list[tuple] = []
    s = Settings(briefing_dir=str(tmp_path / "out"))
    out = P.generate_briefing(
        store.get(job.id),
        store,
        answers={},
        skipped=[],
        settings=s,
        provider=StubProvider(),
        emit=lambda ev, payload: events.append((ev, payload)),
    )
    assert out.status == "ready"
    assert out.briefing_md  # il briefing è comunque generato
    warn_msgs = [
        p
        for (ev, p) in events
        if ev == "warning"
        for m in p.get("messages", [])
        if "vuot" in m.lower() or "sostanz" in m.lower()
    ]
    assert warn_msgs, "atteso un warning sull'analisi vuota"


def test_generate_briefing_no_sparse_warning_when_content_present(store, tmp_path):
    """Controprova: con un'analisi che ha contenuto, NESSUN warning di analisi vuota."""
    full = Analysis(meta=Meta(type="solo", title="Piena"), key_ideas=["un'idea concreta"])
    job = store.create(Job.new(str(tmp_path / "b.wav"), model="small", mode="solo"))
    store.update(job.id, transcript="testo", analysis=full.model_dump(), questions=[], status="awaiting_interview")
    events: list[tuple] = []
    s = Settings(briefing_dir=str(tmp_path / "out2"))
    out = P.generate_briefing(
        store.get(job.id),
        store,
        answers={},
        skipped=[],
        settings=s,
        provider=StubProvider(),
        emit=lambda ev, payload: events.append((ev, payload)),
    )
    assert out.status == "ready"
    sparse_warn = [p for (ev, p) in events if ev == "warning" for m in p.get("messages", []) if "vuot" in m.lower()]
    assert not sparse_warn


def test_generate_briefing_renders_markers_in_artifacts(store, tmp_path, monkeypatch):
    """Seam reale end-to-end: job.markers compaiono nel briefing_md (path 0-domande →
    generate_briefing usa i renderer REALI, solo analyze/whisper sono finti)."""
    analysis = Analysis(meta=Meta(type="solo", title="X"))
    _patch_engine(monkeypatch, analysis, [])  # detect_questions → [] ; analyze → analysis
    job = store.create(
        Job.new(
            str(tmp_path / "a.wav"),
            model="small",
            language="it",
            mode="solo",
            markers=[{"t_ms": 90_000, "label": "Lotto X"}],
        )
    )
    out = P.run_processing(
        job,
        store,
        settings=Settings(briefing_dir=str(tmp_path / "out")),
        provider=StubProvider(),
        emit=lambda ev, payload: None,
    )
    assert out.status == "ready"
    assert "Lotto X" in out.briefing_md
    assert "01:30" in out.briefing_md
    assert "## Segnalibri" in out.recap_md


# ── L09: warning lingua configurata ≠ rilevata ───────────────────────────────


def test_language_warning_mismatch():
    from app.pipeline import _language_warning

    msg = _language_warning("it", "en", 0.95)
    assert msg and "inglese" in msg.lower() and "it" in msg.lower()


def test_language_warning_none_when_match():
    from app.pipeline import _language_warning

    assert _language_warning("it", "it", 0.99) is None


def test_language_warning_none_when_low_confidence_mismatch():
    """Mismatch ma confidenza bassa (<0.66) → niente allarme (rilevazione inaffidabile)."""
    from app.pipeline import _language_warning

    assert _language_warning("it", "en", 0.4) is None


def test_language_warning_uncertain_multilang():
    """Confidenza molto bassa (<0.5) con lingua rilevata → avviso 'incerta/multilingua'."""
    from app.pipeline import _language_warning

    msg = _language_warning("auto", "it", 0.42)
    assert msg and ("incert" in msg.lower() or "multiling" in msg.lower())


def test_language_warning_none_when_auto_and_confident():
    from app.pipeline import _language_warning

    assert _language_warning("auto", "it", 0.95) is None


def test_run_processing_warns_on_language_mismatch(store, tmp_path, monkeypatch):
    """Seam: se la lingua rilevata ≠ configurata (con confidenza), run_processing emette un warning."""
    monkeypatch.setattr(P.models_mod, "is_downloaded", lambda name: True)

    def fake_stream(path, *, model, language, on_segment=None, should_cancel=None):
        if on_segment:
            on_segment(1.0, "hello world", "hello world", from_cache=False)
        return {
            "source": path,
            "model": model,
            "language": language,
            "detected_language": "en",
            "language_probability": 0.96,
            "duration_s": 5.0,
            "segments": [],
            "text": "hello world",
        }

    monkeypatch.setattr(P.whisper_mod, "transcribe_stream", fake_stream)

    # analisi finta per non chiamare l'LLM reale
    monkeypatch.setattr(
        P.analyzer_mod,
        "analyze",
        lambda text, **kw: Analysis(meta=Meta(type="solo"), key_ideas=["x"]),
    )
    monkeypatch.setattr(P.interview_mod, "detect_questions", lambda *a, **k: [])

    events: list[tuple] = []
    job = store.create(Job.new(str(tmp_path / "a.wav"), model="large-v3-turbo", mode="solo", language="it"))
    P.run_processing(
        job,
        store,
        settings=Settings(briefing_dir=str(tmp_path / "o")),
        provider=StubProvider(),
        emit=lambda ev, p: events.append((ev, p)),
    )
    lang_warn = [p for (ev, p) in events if ev == "warning" for m in p.get("messages", []) if "inglese" in m.lower()]
    assert lang_warn, "atteso un warning di lingua sbagliata"
