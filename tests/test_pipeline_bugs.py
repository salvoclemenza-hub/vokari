"""Test bugfix pipeline.py: I2, M1, M2, M3."""

import pytest

# ---------------------------------------------------------------------------
# Bug-T3 (I2) — generate_briefing emette status=cancelled prima di ritornare
# ---------------------------------------------------------------------------


def test_generate_briefing_emits_cancelled_when_job_already_cancelled(tmp_path):
    from app import pipeline
    from app.jobs import Job, JobStore

    emitted = []
    store = JobStore(jobs_dir=str(tmp_path / "jobs"))
    job = store.create(Job.new("/tmp/x.wav", title="T"))
    store.update(job.id, status="cancelled")
    pipeline.generate_briefing(
        store.get(job.id),
        store,
        {},
        [],
        emit=lambda ev, p: emitted.append((ev, p)),
    )
    assert any(ev == "status" and p.get("status") == "cancelled" for ev, p in emitted)


# ---------------------------------------------------------------------------
# Bug-T5 (M1) — is_up chiamato una sola volta nel pre-flight Ollama
# ---------------------------------------------------------------------------


def test_m1_is_up_called_once_when_ollama_already_up(tmp_path, monkeypatch):
    from app import pipeline
    from app.jobs import Job, JobStore

    import vokari.llm.ollama_provider as op
    import vokari.settings as sm
    import vokari.transcribe.whisper as wmod

    is_up_calls = []
    monkeypatch.setattr(op, "is_up", lambda ep: is_up_calls.append(ep) or True)

    class _StopEarly(Exception):
        pass

    monkeypatch.setattr(
        wmod,
        "transcribe_stream",
        lambda *a, **kw: (_ for _ in ()).throw(_StopEarly()),
    )
    s = sm.load()
    s.brain = "ollama"
    monkeypatch.setattr(sm, "load", lambda: s)
    store = JobStore(jobs_dir=str(tmp_path / "jobs"))
    job = store.create(Job.new(str(tmp_path / "x.wav"), title="T"))
    with pytest.raises(_StopEarly):
        pipeline.run_processing(job, store, settings=s)
    assert len(is_up_calls) == 1


# ---------------------------------------------------------------------------
# Bug-T6 (M2) — _briefing_out_path con audio_path vuoto ritorna path assoluto
# ---------------------------------------------------------------------------


def test_m2_briefing_out_path_empty_audio_path_is_absolute(tmp_path, monkeypatch):
    from app.jobs import Job
    from app.pipeline import _briefing_out_path

    import vokari.settings as sm

    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    s = sm.load()
    s.briefing_dir = ""
    job = Job.new("", title="test audio vuoto")
    path = _briefing_out_path(s, job)
    assert path.is_absolute()
    assert ".briefing.md" in path.name


# ---------------------------------------------------------------------------
# Bug-T6 (M3-a + M3-b) — run_processing 0-domande: generate_briefing fallisce
#   → job in error, niente re-raise
# ---------------------------------------------------------------------------


def test_m3_run_processing_generate_briefing_failure_returns_error_job(tmp_path, monkeypatch):
    from app import pipeline
    from app.jobs import Job, JobStore

    import vokari.analyze.analyzer as amod
    import vokari.analyze.interview as imod
    import vokari.settings as sm
    import vokari.transcribe.whisper as wmod
    from vokari.analyze.schema import Analysis, Meta
    from vokari.render import briefing as bmod

    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    s = sm.load()
    s.brain = "claude"
    monkeypatch.setattr(sm, "load", lambda: s)
    monkeypatch.setattr(
        wmod,
        "transcribe_stream",
        lambda *a, **kw: {"text": "testo di test", "duration_s": 5.0, "cancelled": False},
    )
    monkeypatch.setattr(
        amod,
        "analyze",
        lambda *a, **kw: Analysis(meta=Meta()),
    )
    monkeypatch.setattr(imod, "detect_questions", lambda *a, **kw: [])

    def _fail_render(*a, **kw):
        raise RuntimeError("render fallito nel test M3")

    monkeypatch.setattr(bmod, "render_briefing", _fail_render)

    class _FakeProv:
        def chat_json(self, *a, **kw):
            return {}

        def chat_text(self, *a, **kw):
            return ""

    store = JobStore(jobs_dir=str(tmp_path / "jobs"))
    job = store.create(Job.new(str(tmp_path / "x.wav"), title="T"))
    result = pipeline.run_processing(job, store, settings=s, provider=_FakeProv())
    assert result.status == "error"
    assert "render fallito" in (result.error or "")


def test_m3b_run_processing_generate_briefing_failure_does_not_reraise(tmp_path, monkeypatch):
    """M3-b: nessun re-raise quando generate_briefing fallisce nel path 0-domande."""
    from app import pipeline
    from app.jobs import Job, JobStore

    import vokari.analyze.analyzer as amod
    import vokari.analyze.interview as imod
    import vokari.settings as sm
    import vokari.transcribe.whisper as wmod
    from vokari.analyze.schema import Analysis, Meta
    from vokari.render import briefing as bmod

    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    s = sm.load()
    s.brain = "claude"
    monkeypatch.setattr(sm, "load", lambda: s)
    monkeypatch.setattr(
        wmod,
        "transcribe_stream",
        lambda *a, **kw: {"text": "testo di test", "duration_s": 5.0, "cancelled": False},
    )
    monkeypatch.setattr(
        amod,
        "analyze",
        lambda *a, **kw: Analysis(meta=Meta()),
    )
    monkeypatch.setattr(imod, "detect_questions", lambda *a, **kw: [])

    def _fail_render(*a, **kw):
        raise RuntimeError("render fallito M3-b")

    monkeypatch.setattr(bmod, "render_briefing", _fail_render)

    class _FakeProv:
        def chat_json(self, *a, **kw):
            return {}

        def chat_text(self, *a, **kw):
            return ""

    store = JobStore(jobs_dir=str(tmp_path / "jobs"))
    job = store.create(Job.new(str(tmp_path / "x.wav"), title="T"))
    # NON deve sollevare eccezione — run_processing ritorna il job in error
    result = pipeline.run_processing(job, store, settings=s, provider=_FakeProv())
    assert result.status == "error"
