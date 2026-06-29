"""Test di CONTRATTO backend↔frontend (anti-drift).

VOKARI ha un contratto implicito tra Python (app/api.py, app/pipeline.py) e il frontend
(frontend/src/bridge.ts): nomi degli eventi push, chiavi camelCase dei dict di ritorno,
stati job. Un rename lato backend rompe la UI in SILENZIO (nessun errore TS né Python).

Questi test fissano il contratto: se il backend cambia un nome evento o una chiave di un
dict, un test diventa ROSSO → il drift va sistemato (aggiornando ANCHE bridge.ts) invece di
scoprirlo a runtime nella finestra pywebview. Le costanti qui sotto DEVONO restare allineate
con le interface in frontend/src/bridge.ts (sono la stessa fonte di verità, lati opposti).
"""

import re
from pathlib import Path

from app.api import Api, _job_view, _session_list_item
from app.jobs import Job, JobStore

from vokari.store.session import Session
from vokari.store.sessions_repo import SessionsRepo

_ROOT = Path(__file__).resolve().parent.parent

# ── Contratto: chiavi camelCase dei dict (== bridge.ts interfaces) ────────────
JOB_VIEW_KEYS = {
    "jobId",
    "title",
    "status",
    "pct",
    "source",
    "mode",
    "model",
    "language",
    "partialText",
    "transcript",
    "durationS",
    "questions",
    "markers",
    "briefingMd",
    "draftBriefing",
    "briefingPath",
    "error",
}
SETTINGS_KEYS = {
    "brain",
    "ollamaEndpoint",
    "ollamaModel",
    "whisperModel",
    "claudeModel",
    "briefingDir",
    "obsidianVault",
    "defaultMode",
    "transcriptionLanguage",
    "livePreview",
    "liveModel",
    "hasApiKey",
    "onboarded",
    "lastSeenVersion",
    "appLanguage",
    "userContext",
}
ARTIFACTS_KEYS = {
    "title",
    "briefingMd",
    "briefingPath",
    "recapMd",
    "obsidianNote",
    "transcriptText",
    "durationS",
    "model",
    "language",
    "wordCount",
}
SESSION_ITEM_KEYS = {
    "id",
    "title",
    "createdAt",
    "mode",
    "model",
    "durationMs",
    "hasBriefing",
    "hasRecap",
    "hasObsidian",
    "clarCount",
    "hasAudio",
}
# Stati job (== type JobStatus in bridge.ts)
JOB_STATUSES = {
    "queued",
    "transcribing",
    "analyzing",
    "rendering",
    "awaiting_edit",
    "awaiting_interview",
    "awaiting_fit_decision",
    "ready",
    "error",
    "cancelled",
}
# Eventi push (== nomi gestiti in App.tsx/Live.tsx/Sidebar.tsx via onVokariEvent)
EVENTS = {
    "status",
    "transcribe_progress",
    "audio_level",
    "live_transcript",
    "model_download",
    "warning",
    "resource_usage",
    "lhm_progress",
    "ollama_pull",
    "ollama_setup",
    "analysis_preview",
    "analyze_step",
    "analysis_fit",
}


def _isolated_api(tmp_path):
    return Api(
        store=JobStore(jobs_dir=str(tmp_path / "jobs")), sessions=SessionsRepo(sessions_dir=str(tmp_path / "sessions"))
    )


def test_job_view_keys_match_contract():
    keys = set(_job_view(Job.new("/x.wav")).keys())
    assert keys == JOB_VIEW_KEYS, f"drift JobView: {keys ^ JOB_VIEW_KEYS}"


def test_get_settings_keys_match_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    keys = set(_isolated_api(tmp_path).get_settings().keys())
    assert keys == SETTINGS_KEYS, f"drift VokariSettings: {keys ^ SETTINGS_KEYS}"


def test_get_artifacts_keys_match_contract(tmp_path):
    api = _isolated_api(tmp_path)
    job = api._store.create(Job.new("/x.wav", title="T", transcript="due parole"))
    keys = set(api.get_artifacts(job.id).keys())
    assert keys == ARTIFACTS_KEYS, f"drift Artifacts: {keys ^ ARTIFACTS_KEYS}"


def test_open_session_returns_artifacts_shape(tmp_path):
    api = _isolated_api(tmp_path)
    sess = Session(
        id="s1",
        title="T",
        created_at="2026-06-10T00:00:00",
        mode="solo",
        source="mic",
        model="small",
        language="it",
        duration_ms=1000,
        transcript="due parole",
        word_count=2,
        status="ready",
        artifacts={"briefing_md": "x", "recap_md": "y", "obsidian_note": "z"},
    )
    api._sessions.save(sess)
    keys = set(api.open_session("s1").keys())
    assert keys == ARTIFACTS_KEYS, f"drift open_session: {keys ^ ARTIFACTS_KEYS}"


def test_session_list_item_keys_match_contract():
    sess = Session(
        id="s1",
        title="T",
        created_at="2026-06-10T00:00:00",
        mode="solo",
        source="mic",
        model="small",
        language="it",
        duration_ms=1000,
        transcript="x",
        word_count=1,
        status="ready",
        artifacts={},
    )
    keys = set(_session_list_item(sess).keys())
    assert keys == SESSION_ITEM_KEYS, f"drift SessionItem: {keys ^ SESSION_ITEM_KEYS}"


def test_emitted_events_are_declared_in_contract():
    """Ogni evento emesso da api.py/pipeline.py deve essere nel set EVENTS (== gestiti dal
    frontend). Un evento nuovo/rinominato non dichiarato qui = drift → aggiorna ANCHE bridge.ts."""
    emitted: set[str] = set()
    for rel in ("app/api.py", "app/pipeline.py"):
        src = (_ROOT / rel).read_text(encoding="utf-8")
        # Pattern ampliato: cattura emit("x"), _emit("x"), self._emit("x")
        emitted |= set(re.findall(r'emit\s*\(\s*["\']([a-z_]+)["\']', src))
    unknown = emitted - EVENTS
    assert not unknown, f"eventi emessi NON dichiarati nel contratto (drift): {unknown}"


def test_transcribe_progress_payload_has_required_keys():
    """Il payload di transcribe_progress deve avere text (str) e pct (float)."""
    src = (_ROOT / "app" / "pipeline.py").read_text(encoding="utf-8")
    pattern = re.compile(
        r'emit\s*\(\s*["\']transcribe_progress["\'].*?\{([^}]+)\}',
        re.DOTALL,
    )
    m = pattern.search(src)
    assert m, "emit transcribe_progress non trovato in pipeline.py"
    payload_str = m.group(1)
    assert '"text"' in payload_str or "'text'" in payload_str, "payload transcribe_progress manca chiave 'text'"
    assert '"pct"' in payload_str or "'pct'" in payload_str, "payload transcribe_progress manca chiave 'pct'"


def test_job_status_event_payloads_use_declared_statuses():
    """Gli stati emessi nell'evento `status` (_emit("status", {"status": "X"})) in pipeline.py
    devono essere nel contratto JOB_STATUSES (== type JobStatus in bridge.ts)."""
    src = (_ROOT / "app" / "pipeline.py").read_text(encoding="utf-8")
    # cattura SOLO gli status dell'evento `status` (_emit("status", {..., "status": "X"})),
    # non quelli di altri eventi come model_download (start/progress/done).
    used = set(re.findall(r'emit\(\s*"status"\s*,\s*\{[^}]*?"status":\s*"([a-z_]+)"', src))
    unknown = used - JOB_STATUSES
    assert not unknown, f"stati job non dichiarati nel contratto (drift): {unknown}"


def test_analysis_preview_payload_has_required_keys():
    """Il payload di analysis_preview deve avere jobId e text."""
    src = (_ROOT / "app" / "pipeline.py").read_text(encoding="utf-8")
    pattern = re.compile(
        r'emit\s*\(\s*["\']analysis_preview["\'].*?\{([^}]+)\}',
        re.DOTALL,
    )
    m = pattern.search(src)
    assert m, "emit analysis_preview non trovato in pipeline.py"
    payload_str = m.group(1)
    assert "jobId" in payload_str, "payload analysis_preview manca chiave 'jobId'"
    assert "text" in payload_str or '"text"' in payload_str, "payload analysis_preview manca chiave 'text'"


def test_analysis_fit_payload_has_required_keys():
    """Il payload di analysis_fit deve avere jobId, level, tokensEst e recommendation."""
    src = (_ROOT / "app" / "pipeline.py").read_text(encoding="utf-8")
    pattern = re.compile(
        r'emit\s*\(\s*["\']analysis_fit["\'].*?\{([^}]+)\}',
        re.DOTALL,
    )
    m = pattern.search(src)
    assert m, "emit analysis_fit non trovato in pipeline.py"
    payload_str = m.group(1)
    for key in ("jobId", "level", "tokensEst", "recommendation"):
        assert key in payload_str, f"payload analysis_fit manca chiave '{key}'"


def test_analyze_step_payload_has_required_keys():
    """Il payload di analyze_step deve avere jobId, step e label."""
    src = (_ROOT / "app" / "pipeline.py").read_text(encoding="utf-8")
    pattern = re.compile(
        r'emit\s*\(\s*["\']analyze_step["\'].*?\{([^}]+)\}',
        re.DOTALL,
    )
    m = pattern.search(src)
    assert m, "emit analyze_step non trovato in pipeline.py"
    payload_str = m.group(1)
    assert "jobId" in payload_str, "payload analyze_step manca chiave 'jobId'"
    assert "step" in payload_str, "payload analyze_step manca chiave 'step'"
    assert "label" in payload_str, "payload analyze_step manca chiave 'label'"
