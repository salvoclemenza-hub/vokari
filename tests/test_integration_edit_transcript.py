"""N1 — Integration test headless del flusso REALE editing trascrizione.

Tocca i seam veri (lezione ADR-010: i test mockati nascondono il path felice rotto):
- `Api.import_file` → `_spawn_processing` → **vera** `pipeline.run_processing` (edit_gate ON
  perché `_window` è impostato) → si ferma al gate `awaiting_edit`;
- `Api.update_transcript` salva l'edit su `JobStore`;
- `Api.resume_job` → `_spawn_processing(skip_transcribe=True)` → **vera** `run_processing` che
  NON ritrascrive e passa il transcript EDITATO all'analizzatore.

Solo i confini del motore sono finti (whisper/analyze/provider), come i real-seam test di
`test_pipeline.py`. L'asserzione cardine: l'analisi riceve il testo CORRETTO A MANO, non il grezzo.
"""

import pytest
from app import pipeline as P
from app.api import Api
from app.jobs import JobStore

from vokari.analyze.schema import Analysis, Meta
from vokari.settings import Settings
from vokari.store.sessions_repo import SessionsRepo


class _FakeWindow:
    """Finestra finta: rende `_window is not None` (gate fit+edit attivi) e assorbe gli emit."""

    def evaluate_js(self, js: str) -> None:
        pass


class _StubProvider:
    def chat_json(self, system, user):
        return {}

    def chat_text(self, system, user):
        return ""


@pytest.fixture
def sync_threads(monkeypatch):
    """Esegue i thread daemon dell'Api in modo SINCRONO → determinismo (start() = chiamata diretta)."""
    import app.api as apimod

    monkeypatch.setattr(
        apimod.threading, "Thread", lambda target, daemon=None: type("T", (), {"start": staticmethod(target)})()
    )


def test_edit_transcript_flows_edited_text_to_analysis(tmp_path, monkeypatch, sync_threads):
    # --- motore finto ai confini ----------------------------------------------------------
    captured: dict = {}

    def fake_stream(path, *, model, language, on_segment=None, should_cancel=None, **_kw):
        # trascrizione "grezza" con un errore di riconoscimento (Giovanni→Gianni)
        return {"text": "Giovanni ha sforato il bilancio", "duration_s": 9.0}

    def fake_analyze(text, **_kw):
        captured["analyze_text"] = text
        return Analysis(meta=Meta(type="solo", title="X"))

    # ffprobe via subprocess crea Thread interni con args= → incompatibile con sync_threads (che
    # patcha threading.Thread globalmente). Lo stubbiamo: durata ignota → preflight A1 saltato.
    monkeypatch.setattr(P.convert_mod, "probe_duration_s", lambda path: None)
    monkeypatch.setattr(P.models_mod, "is_downloaded", lambda name: True)
    monkeypatch.setattr(P.whisper_mod, "transcribe_stream", fake_stream)
    monkeypatch.setattr(P.analyzer_mod, "analyze", fake_analyze)
    monkeypatch.setattr(P.interview_mod, "detect_questions", lambda *a, **k: [])
    monkeypatch.setattr(P, "make_provider", lambda s: _StubProvider())
    # Settings deterministiche (le reali dell'utente sono brain=ollama → preflight reale): brain
    # claude + provider finto → niente dipendenza da Ollama/rete. Tocca app.api e app.pipeline (stesso modulo).
    monkeypatch.setattr(P.settings_mod, "load", lambda: Settings(brain="claude", briefing_dir=str(tmp_path / "out")))

    # --- Api reale con finestra (gate editing attivo) -------------------------------------
    api = Api(store=JobStore(jobs_dir=tmp_path / "jobs"), sessions=SessionsRepo(sessions_dir=tmp_path / "sessions"))
    api._window = _FakeWindow()

    audio = tmp_path / "riunione.m4a"
    audio.write_bytes(b"\x00\x01\x02\x03")  # file non vuoto: supera il gate di import_file

    # 1) import → la pipeline si ferma al gate editing PRIMA di analizzare
    r = api.import_file(str(audio), mode="solo", title="Riunione")
    jid = r["jobId"]
    job = api._store.get(jid)
    assert job.status == "awaiting_edit", "la pipeline deve fermarsi al gate editing con la GUI"
    assert job.transcript == "Giovanni ha sforato il bilancio"  # testo grezzo salvato per la revisione
    assert "analyze_text" not in captured, "l'analisi NON deve partire prima della revisione"

    # 2) l'utente corregge il testo
    out = api.update_transcript(jid, "Gianni ha rispettato il bilancio")
    assert out.get("success") is True
    assert api._store.get(jid).transcript_edited is True

    # 3) Procedi → resume: l'analisi riceve il testo EDITATO (non il grezzo), senza ritrascrivere
    api.resume_job(jid)
    assert captured.get("analyze_text") == "Gianni ha rispettato il bilancio"
    assert api._store.get(jid).status == "awaiting_interview"


def test_resume_without_edit_uses_original_transcript(tmp_path, monkeypatch, sync_threads):
    """Se l'utente procede senza modificare, l'analisi riceve comunque il transcript originale
    (skip_transcribe legge dal job) e il flusso arriva ad awaiting_interview."""
    captured: dict = {}

    # ffprobe via subprocess crea Thread interni con args= → incompatibile con sync_threads (che
    # patcha threading.Thread globalmente). Lo stubbiamo: durata ignota → preflight A1 saltato.
    monkeypatch.setattr(P.convert_mod, "probe_duration_s", lambda path: None)
    monkeypatch.setattr(P.models_mod, "is_downloaded", lambda name: True)
    monkeypatch.setattr(
        P.whisper_mod, "transcribe_stream", lambda *a, **k: {"text": "testo originale intatto", "duration_s": 4.0}
    )
    monkeypatch.setattr(
        P.analyzer_mod, "analyze", lambda text, **_kw: (captured.__setitem__("t", text), Analysis(meta=Meta()))[1]
    )
    monkeypatch.setattr(P.interview_mod, "detect_questions", lambda *a, **k: [])
    monkeypatch.setattr(P, "make_provider", lambda s: _StubProvider())
    monkeypatch.setattr(P.settings_mod, "load", lambda: Settings(brain="claude", briefing_dir=str(tmp_path / "out")))

    api = Api(store=JobStore(jobs_dir=tmp_path / "jobs"), sessions=SessionsRepo(sessions_dir=tmp_path / "sessions"))
    api._window = _FakeWindow()
    audio = tmp_path / "a.m4a"
    audio.write_bytes(b"\x00\x01")

    jid = api.import_file(str(audio), mode="solo")["jobId"]
    assert api._store.get(jid).status == "awaiting_edit"
    # nessuna chiamata a update_transcript: procede subito
    api.resume_job(jid)
    assert captured.get("t") == "testo originale intatto"
    assert api._store.get(jid).status == "awaiting_interview"
    assert api._store.get(jid).transcript_edited is False
