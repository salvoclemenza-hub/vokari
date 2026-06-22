from pathlib import Path

import pytest
from app.api import Api
from app.jobs import Job, JobStore

from vokari.store.sessions_repo import SessionsRepo


class FakeWindow:
    def __init__(self):
        self.calls: list[str] = []

    def evaluate_js(self, js: str):
        self.calls.append(js)


@pytest.fixture
def api(tmp_path):
    a = Api(store=JobStore(jobs_dir=tmp_path / "jobs"), sessions=SessionsRepo(sessions_dir=tmp_path / "sessions"))
    a._window = FakeWindow()
    return a


@pytest.fixture
def sync_threads(monkeypatch):
    """Esegue i thread daemon dell'Api in modo SINCRONO (determinismo nei test):
    .start() chiama subito il target. Riusato per generate() che ora gira off-thread (C1)."""
    import app.api as apimod

    monkeypatch.setattr(
        apimod.threading, "Thread", lambda target, daemon=None: type("T", (), {"start": staticmethod(target)})()
    )


def test_get_app_info_unchanged(api):
    info = api.get_app_info()
    assert info["license"] == "MIT" and "githubStars" in info


def test_import_file_derives_title_from_filename(api, monkeypatch, tmp_path):
    """B3: importando un file senza titolo esplicito, il titolo viene dal nome file
    (es. '183.m4a' → '183') invece dell'ennesima 'Sessione senza titolo'."""
    monkeypatch.setattr(api, "_spawn_processing", lambda job: None)  # niente pipeline reale
    # path costruito con l'OS corrente: Path(...).stem funziona su Windows e in CI Linux
    # (un path Windows hardcoded come C:\audio\183.m4a non si splitta su POSIX → stem errato).
    out = api.import_file(str(tmp_path / "183.m4a"))
    job = api._store.get(out["jobId"])
    assert job.title == "183"


def test_import_file_keeps_explicit_title(api, monkeypatch, tmp_path):
    monkeypatch.setattr(api, "_spawn_processing", lambda job: None)
    out = api.import_file(str(tmp_path / "183.m4a"), title="Riunione marketing")
    assert api._store.get(out["jobId"]).title == "Riunione marketing"


def test_save_session_skips_empty_transcript(api):
    """B2: un job senza parlato non finisce nella libreria (niente '00:00 / senza titolo')."""
    job = api._store.create(Job.new("/tmp/x.wav", title="vuota", status="ready"))
    api._save_session(job)
    assert api.list_sessions() == []


def test_save_session_persists_when_transcript_present(api):
    job = api._store.create(Job.new("/tmp/x.wav", title="vera", status="ready"))
    api._store.update(job.id, transcript="ciao questo è un test", duration_s=12.0)
    api._save_session(api._store.get(job.id))
    sessions = api.list_sessions()
    assert len(sessions) == 1 and sessions[0]["title"] == "vera"


def test_shutdown_abandons_all_midflight_jobs(api):
    """A1: chiudendo la finestra TUTTI i job midflight — incluso awaiting_interview —
    diventano 'cancelled' → al riavvio non resuscitano e l'app non nag "elaborazione in
    corso" (feedback 2026-06-15)."""
    t = api._store.create(Job.new("/tmp/t.wav"))
    api._store.update(t.id, status="transcribing")
    iv = api._store.create(Job.new("/tmp/i.wav"))
    api._store.update(iv.id, status="awaiting_interview")
    api.shutdown()
    assert api._store.get(t.id).status == "cancelled"
    assert api._store.get(iv.id).status == "cancelled"


def test_emit_calls_window_evaluate_js(api):
    api._emit("status", {"jobId": "x", "status": "ready"})
    assert api._window.calls and api._window.calls[0].startswith("window.__vokari_emit(")
    assert '"jobId"' in api._window.calls[0]


def test_generate_runs_pipeline_in_thread(api, monkeypatch, sync_threads, tmp_path):
    """generate() ritorna SUBITO il job corrente (C1: niente blocco del thread pywebview)
    e fa girare la generazione off-thread (qui sincrono) fino a ready."""
    job = api._store.create(Job.new(str(tmp_path / "a.wav"), mode="solo"))
    api._store.update(
        job.id, transcript="t", analysis={"meta": {"type": "solo"}}, questions=[], status="awaiting_interview"
    )

    def fake_generate(j, store, answers, skipped, *, settings=None, provider=None, emit=None):
        return store.update(j.id, status="ready", briefing_md="# B", briefing_path="/x/b.md")

    monkeypatch.setattr(api, "_generate_impl", fake_generate)
    out = api.generate(job.id, {"q1": "x"}, [])
    assert out["jobId"] == job.id  # ritorno immediato (pre-generazione)
    final = api.get_job(job.id)  # il thread (sincrono) ha portato il job a ready
    assert final["status"] == "ready"
    assert final["briefingMd"] == "# B" and final["briefingPath"] == "/x/b.md"


def test_generate_emits_error_status_on_exception(api, monkeypatch, sync_threads, tmp_path):
    """Se _generate_impl solleva (es. LLM giù), il job va in error e lo status=error
    viene EMESSO alla UI: la finestra non resta bloccata su 'processing' (C1)."""
    job = api._store.create(Job.new(str(tmp_path / "a.wav"), mode="solo"))
    api._store.update(job.id, status="awaiting_interview")

    def boom(*a, **k):
        raise RuntimeError("LLM non raggiungibile")

    monkeypatch.setattr(api, "_generate_impl", boom)
    api.generate(job.id, {}, [])
    assert api._store.get(job.id).status == "error"
    assert "LLM non raggiungibile" in api._store.get(job.id).error
    assert any('"status": "error"' in c for c in api._window.calls), "lo status=error deve essere emesso al frontend"


def test_get_active_job_none_when_empty(api):
    assert api.get_active_job() is None


def test_stop_recording_returns_immediately_and_finalizes(tmp_path, monkeypatch):
    import time

    from app.api import Api
    from app.jobs import JobStore

    api = Api(store=JobStore(jobs_dir=str(tmp_path / "jobs")))

    wav = tmp_path / "out.wav"
    wav.write_bytes(b"RIFF")  # placeholder; la pipeline è stubbata sotto

    class _FakeResult:
        def __init__(self):
            self.wav_path = str(wav)
            self.source = "both"
            self.markers = []
            self.warnings = []

    class _FakeRec:
        def stop(self):
            time.sleep(0.3)
            return _FakeResult()

    api._rec = _FakeRec()

    started = {}
    monkeypatch.setattr(api, "_spawn_processing", lambda job: started.setdefault("id", job.id))

    t0 = time.time()
    res = api.stop_recording(mode="solo", title="X")
    assert time.time() - t0 < 0.1, "stop_recording deve ritornare subito (finalizza in background)"
    assert res["jobId"]
    for _ in range(50):
        if started.get("id") == res["jobId"]:
            break
        time.sleep(0.02)
    assert started.get("id") == res["jobId"]
    job = api._store.get(res["jobId"])
    assert job.audio_path == str(wav)


def test_flash_taskbar_no_window_is_noop(api):
    """Senza finestra nativa flash_taskbar non solleva e ritorna ok=False (FS1)."""
    api._window = None
    assert api.flash_taskbar() == {"ok": False}


def test_browse_audio_file_no_window_returns_empty_path():
    """Con _window=None il metodo ritorna {"path": ""} senza aprire dialogo."""
    a = Api()
    a._window = None
    result = a.browse_audio_file()
    assert result == {"path": ""}


def test_invalidate_transcript_cache_deletes_file_and_requeues(tmp_path):
    """invalidate_transcript_cache cancella il file cache + rimette il job in queued."""
    import json as _json

    from vokari.transcribe.whisper import _cache_path, audio_hash

    audio = tmp_path / "rec.wav"
    audio.write_bytes(b"\x00" * 100)
    store = JobStore(jobs_dir=tmp_path / "jobs")
    store.create(
        Job(
            id="j1",
            audio_path=str(audio),
            model="large-v3-turbo",
            language="it",
            mode="solo",
            title="test",
            status="transcribing",
        )
    )
    key = f"{audio_hash(str(audio))}-large-v3-turbo-it"
    cache_file = _cache_path(key)
    cache_file.write_text(_json.dumps({"text": "cached"}), encoding="utf-8")
    api = Api.__new__(Api)
    api._store = store
    api._window = None
    result = api.invalidate_transcript_cache("j1")
    assert result == {"ok": True}
    assert not cache_file.exists()
    assert store.get("j1").status == "queued"


def test_stop_recording_uses_settings_default_mode(api, monkeypatch, tmp_path):
    from types import SimpleNamespace

    import app.api as apimod

    from vokari.settings import Settings

    monkeypatch.setattr(
        apimod.settings_mod,
        "load",
        lambda: Settings(default_mode="riunione", whisper_model="small", transcription_language="it"),
    )

    class FakeRec:
        def stop(self):
            return SimpleNamespace(wav_path=str(tmp_path / "a.wav"), source="mic", duration_s=1.0, markers=[])

    api._rec = FakeRec()
    # evita che parta davvero il thread di pipeline
    monkeypatch.setattr(api, "_spawn_processing", lambda job: None)

    res = api.stop_recording()  # nessun mode passato
    job = api._store.get(res["jobId"])
    assert job.mode == "riunione"


def test_start_recording_discards_previous_recording(tmp_path, monkeypatch):
    """start_recording con una registrazione già attiva la scarta (no Recorder/LiveTranscriber
    orfani): rec.stop()/live.stop() vengono chiamati e i ref puntano alla NUOVA cattura."""
    import app.api as apimod
    from app.api import Api
    from app.jobs import JobStore

    from vokari import settings as settings_mod
    from vokari.audio import capture
    from vokari.settings import Settings

    monkeypatch.setattr(settings_mod, "load", lambda: Settings(live_preview=False))
    # il discard del precedente gira in un thread daemon → rendilo sincrono per il test
    monkeypatch.setattr(
        apimod.threading, "Thread", lambda target, daemon=None: type("T", (), {"start": staticmethod(target)})()
    )

    class _NewRec:
        def __init__(self, *a, **k):
            pass

        def start(self):
            pass

    monkeypatch.setattr(capture, "Recorder", _NewRec)

    stopped = {"rec": False, "live": False}

    class _PrevRec:
        def stop(self):
            stopped["rec"] = True

    class _PrevLive:
        def stop(self):
            stopped["live"] = True

    api = Api(store=JobStore(jobs_dir=str(tmp_path / "jobs")))
    api._rec = _PrevRec()
    api._live = _PrevLive()

    api.start_recording("mic")
    assert stopped["rec"] is True and stopped["live"] is True, "la registrazione precedente va scartata"
    assert isinstance(api._rec, _NewRec), "i ref devono puntare alla nuova cattura"
    assert api._live is None


def test_stop_recording_captures_live_locally(tmp_path, monkeypatch):
    """stop_recording cattura _live in un locale e azzera self._live SUBITO: _finalize ferma
    il live catturato, non self._live (che una nuova start_recording potrebbe riassegnare)."""
    import app.api as apimod
    from app.api import Api
    from app.jobs import JobStore

    from vokari.audio.capture import CaptureResult

    monkeypatch.setattr(
        apimod.threading, "Thread", lambda target, daemon=None: type("T", (), {"start": staticmethod(target)})()
    )

    live_stopped = {"v": False}

    class _Live:
        def stop(self):
            live_stopped["v"] = True

    class _Rec:
        def stop(self):
            return CaptureResult(str(tmp_path / "x.wav"), 1.0, "both")

    api = Api(store=JobStore(jobs_dir=str(tmp_path / "jobs")))
    api._rec = _Rec()
    api._live = _Live()
    monkeypatch.setattr(api, "_spawn_processing", lambda job: None)

    res = api.stop_recording(mode="solo", title="X")
    assert res["jobId"]
    assert api._rec is None and api._live is None  # azzerati subito sul thread js-api
    assert live_stopped["v"] is True  # _finalize ha fermato il live catturato


# ─────────────────────────────────────────────────────────────────────────────
# WP5 (F8) — 0 domande: la pipeline arriva a ready e _spawn_processing salva la sessione
# ─────────────────────────────────────────────────────────────────────────────


def test_spawn_processing_saves_session_when_pipeline_returns_ready(api, monkeypatch, tmp_path):
    """Se run_processing torna un job ready (caso 0-domande), _spawn_processing.run()
    deve salvare la sessione UNA volta (la pipeline non passa da generate())."""
    import threading as _t

    import app.api as apimod

    job = api._store.create(Job.new(str(tmp_path / "a.wav"), mode="solo"))

    def fake_run_processing(j, store, emit=None):
        return store.update(j.id, status="ready", briefing_md="# B")

    monkeypatch.setattr(apimod.pipeline_mod, "run_processing", fake_run_processing)

    saved: list[str] = []
    monkeypatch.setattr(api, "_save_session", lambda j: saved.append(j.id))

    # esegui sincrono per determinismo
    monkeypatch.setattr(_t, "Thread", lambda target, daemon=None: type("T", (), {"start": staticmethod(target)})())
    api._spawn_processing(job)

    assert saved == [job.id], "la sessione deve essere salvata esattamente una volta"


def test_spawn_processing_does_not_save_when_awaiting_interview(api, monkeypatch, tmp_path):
    """Se run_processing torna awaiting_interview (≥1 domanda), _spawn_processing NON salva:
    il save scatterà in generate() come prima (no doppio salvataggio)."""
    import threading as _t

    import app.api as apimod

    job = api._store.create(Job.new(str(tmp_path / "a.wav"), mode="solo"))

    def fake_run_processing(j, store, emit=None):
        return store.update(j.id, status="awaiting_interview")

    monkeypatch.setattr(apimod.pipeline_mod, "run_processing", fake_run_processing)

    saved: list[str] = []
    monkeypatch.setattr(api, "_save_session", lambda j: saved.append(j.id))
    monkeypatch.setattr(_t, "Thread", lambda target, daemon=None: type("T", (), {"start": staticmethod(target)})())
    api._spawn_processing(job)

    assert saved == [], "non deve salvare quando il job attende l'intervista"


# ─────────────────────────────────────────────────────────────────────────────
# M7-E — Settings round-trip (seam reale: settings.json su disco + keyring)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_api(tmp_path, monkeypatch):
    """Api con VOKARI_HOME isolato in tmp_path: settings.json e keyring non toccano il sistema."""
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    a = Api(store=JobStore(jobs_dir=tmp_path / "jobs"))
    a._window = FakeWindow()
    return a


def test_get_settings_returns_camel_keys(isolated_api):
    s = isolated_api.get_settings()
    for key in (
        "brain",
        "ollamaEndpoint",
        "whisperModel",
        "claudeModel",
        "briefingDir",
        "obsidianVault",
        "defaultMode",
        "transcriptionLanguage",
        "hasApiKey",
    ):
        assert key in s, f"chiave attesa mancante: {key}"


def test_get_settings_never_returns_api_key_in_plain(isolated_api, monkeypatch):
    import vokari.settings as sm

    monkeypatch.setattr(sm, "get_api_key", lambda: "sk-ant-supersecret")
    s = isolated_api.get_settings()
    # hasApiKey deve essere True ma la chiave NON deve comparire nel dict
    assert s["hasApiKey"] is True
    for v in s.values():
        assert "sk-ant-supersecret" not in str(v), "la chiave API non deve essere restituita in chiaro"


def test_save_settings_round_trip_writes_to_disk(isolated_api, tmp_path):
    """save_settings scrive settings.json sul disco e get_settings legge il nuovo valore."""
    isolated_api.save_settings({"defaultMode": "riunione"})
    # get_settings deve riflettere il valore appena scritto su disco
    s2 = isolated_api.get_settings()
    assert s2["defaultMode"] == "riunione"
    # Verifica seam reale: il file JSON su disco deve contenere la modifica
    import json

    from vokari.paths import app_dirs

    settings_path = app_dirs().config / "settings.json"
    raw = json.loads(settings_path.read_text(encoding="utf-8"))
    assert raw["default_mode"] == "riunione"


def test_save_settings_partial_merge_preserves_other_fields(isolated_api):
    """Un patch parziale non deve cancellare gli altri campi."""
    isolated_api.save_settings({"brain": "ollama"})
    s = isolated_api.get_settings()
    assert s["brain"] == "ollama"
    # transcriptionLanguage deve conservare il valore default
    assert s["transcriptionLanguage"] == "it"


def test_set_api_key_stores_in_keyring_not_json(isolated_api):
    """set_api_key usa il keyring e NON scrive la chiave nel settings.json.
    Il keyring è isolato in-memory da conftest._isolate_keyring → nessun accesso
    al secret store reale (mai più la chiave di produzione cancellata dai test)."""
    import keyring as kr

    result = isolated_api.set_api_key("sk-ant-testkey")
    assert result["ok"] is True
    assert result["hasApiKey"] is True

    # verifica keyring (store in-memory di conftest): la chiave è finita lì
    stored = kr.get_password("vokari", "anthropic_api_key")
    assert stored == "sk-ant-testkey"

    # verifica che NON sia nel settings.json (se esiste)
    import json

    from vokari.paths import app_dirs

    p = app_dirs().config / "settings.json"
    if p.exists():
        raw = json.loads(p.read_text(encoding="utf-8"))
        for v in raw.values():
            assert "sk-ant-testkey" not in str(v), "la chiave non deve essere nel settings.json"


def test_browse_folder_no_window_returns_empty(isolated_api):
    isolated_api._window = None
    res = isolated_api.browse_folder()
    assert res == {"path": ""}


# ─────────────────────────────────────────────────────────────────────────────
# M7-G — Modelli AI (list_models, download_model, set_active_model, set_brain)
# ─────────────────────────────────────────────────────────────────────────────


def test_list_models_returns_entries_with_state(isolated_api, monkeypatch):
    """list_models ritorna una voce per ogni modello del CATALOG con state valido."""
    import vokari.transcribe.models as mmod

    monkeypatch.setattr(mmod, "is_downloaded", lambda name: name == "small")

    result = isolated_api.list_models()
    assert len(result) == len(mmod.CATALOG)

    valid_states = {"active", "downloaded", "available"}
    for entry in result:
        assert "name" in entry
        assert "sizeLabel" in entry
        assert "speed" in entry and "quality" in entry
        assert "languages" in entry
        assert "recommended" in entry
        assert entry["state"] in valid_states, f"state non valido: {entry['state']}"

    # "small" è scaricato ma non è il whisper_model default → "downloaded"
    small = next(e for e in result if e["name"] == "small")
    assert small["state"] == "downloaded"


def test_list_models_active_is_whisper_model(isolated_api, monkeypatch):
    """Il modello uguale a settings.whisper_model che è scaricato deve avere state='active'."""
    import vokari.transcribe.models as mmod

    # large-v3-turbo è il default di Settings; simuliamo che sia scaricato
    monkeypatch.setattr(mmod, "is_downloaded", lambda name: name == "large-v3-turbo")

    result = isolated_api.list_models()
    turbo = next(e for e in result if e["name"] == "large-v3-turbo")
    assert turbo["state"] == "active"


def test_download_model_emits_events_and_returns_ok(isolated_api, monkeypatch):
    """download_model torna subito con ok=True, scarica in background, emette start/done via evento.
    Attende un tick per il thread daemon di essere schedulato."""
    import time

    import vokari.transcribe.models as mmod

    monkeypatch.setattr(mmod, "download", lambda name: "/fake/path")
    monkeypatch.setattr(mmod, "is_downloaded", lambda name: True)

    result = isolated_api.download_model("small")
    assert result["ok"] is True
    # Non c'è "state" nel ritorno immediato (è nel download in background)

    # attendi che il thread spaventi gli eventi
    time.sleep(0.1)

    # verifica eventi push
    calls = isolated_api._window.calls
    starts = [c for c in calls if '"model_download"' in c and '"start"' in c]
    dones = [c for c in calls if '"model_download"' in c and '"done"' in c]
    assert starts, "evento start non emesso"
    assert dones, "evento done non emesso"


def test_download_model_emits_error_on_failure(isolated_api, monkeypatch):
    """Se models.download lancia, download_model emette evento error in background.
    Il ritorno è sempre ok=True (il download è stato queued); l'errore arriva via evento."""
    import time

    import vokari.transcribe.models as mmod

    monkeypatch.setattr(mmod, "download", lambda name: (_ for _ in ()).throw(RuntimeError("rete")))

    result = isolated_api.download_model("small")
    assert result["ok"] is True  # ritorna subito

    # attendi che il thread spaventi l'evento di errore
    time.sleep(0.1)

    errors = [c for c in isolated_api._window.calls if '"error"' in c and '"model_download"' in c]
    assert errors, "evento error non emesso"


def test_expected_bytes_parses_gb():
    import app.api as apimod

    assert apimod._expected_bytes("large-v3-turbo") == 1_600_000_000  # "~1.6 GB"
    assert apimod._expected_bytes("small") == 500_000_000  # "~0.5 GB"
    assert apimod._expected_bytes("inesistente") == 0


def test_download_model_emits_progress(isolated_api, monkeypatch):
    """Durante un download lento, download_model emette eventi progress stimati dalla
    crescita della dir modelli (poll accelerato per il test)."""
    import time

    import app.api as apimod

    import vokari.transcribe.models as mmod
    from vokari.paths import ensure_dirs

    monkeypatch.setattr(apimod, "_DL_POLL_S", 0.02)
    models_dir = ensure_dirs().models

    def fake_download(name):
        (models_dir / "blob.bin").write_bytes(b"\0" * 1_000_000)  # cresce la dir
        time.sleep(0.12)  # tiene occupato il monitor
        return "/fake"

    monkeypatch.setattr(mmod, "download", fake_download)
    isolated_api.download_model("small")
    time.sleep(0.2)

    progress = [c for c in isolated_api._window.calls if '"model_download"' in c and '"progress"' in c]
    assert progress, "nessun evento di progresso emesso"


def test_set_active_model_updates_whisper_model(isolated_api):
    """set_active_model scrive whisper_model e ritorna le settings aggiornate."""
    result = isolated_api.set_active_model("medium")
    assert result["whisperModel"] == "medium"
    # verifica seam reale: get_settings deve riflettere la modifica
    s2 = isolated_api.get_settings()
    assert s2["whisperModel"] == "medium"


def test_set_brain_updates_brain(isolated_api):
    """set_brain scrive brain e ritorna le settings aggiornate."""
    result = isolated_api.set_brain("ollama")
    assert result["brain"] == "ollama"
    s2 = isolated_api.get_settings()
    assert s2["brain"] == "ollama"


# ─────────────────────────────────────────────────────────────────────────────
# M7-F — Sessioni: list_sessions / search_sessions / open_session
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def sessions_api(tmp_path, monkeypatch):
    """Api isolata con VOKARI_HOME in tmp_path (sessions + jobs separati)."""
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    a = Api(store=JobStore(jobs_dir=tmp_path / "jobs"))
    a._window = FakeWindow()
    return a


def _make_ready_job(api, tmp_path, *, recap_md="# Recap\n\nContenuto recap.", obsidian_note="# Nota"):
    """Crea un job in stato ready nello store (senza girare la pipeline reale)."""
    from app.jobs import Job

    audio = str(tmp_path / "a.wav")
    Path(audio).touch()
    job = api._store.create(Job.new(audio, mode="solo", title="Test sessione", model="large-v3-turbo", language="it"))
    api._store.update(
        job.id,
        transcript="trascrizione test",
        duration_s=120.0,
        analysis={"meta": {"type": "solo"}},
        questions=[],
        briefing_md="# Briefing",
        briefing_path="/x/b.md",
        recap_md=recap_md,
        obsidian_note=obsidian_note,
        status="ready",
    )
    return api._store.get(job.id)


def test_generate_saves_session_on_ready(sessions_api, tmp_path, monkeypatch, sync_threads):
    """generate() su job ready salva una Session recuperabile via list_sessions."""
    job = _make_ready_job(sessions_api, tmp_path)

    def fake_generate(j, store, answers, skipped, *, settings=None, provider=None, emit=None):
        return store.update(
            j.id, status="ready", briefing_md="# B", briefing_path="/x/b.md", recap_md="# Recap", obsidian_note="# Nota"
        )

    monkeypatch.setattr(sessions_api, "_generate_impl", fake_generate)
    sessions_api.generate(job.id, {}, [])

    sessions = sessions_api.list_sessions()
    assert len(sessions) == 1
    s = sessions[0]
    assert s["id"] == job.id
    assert "title" in s and "createdAt" in s and "mode" in s
    assert "hasBriefing" in s and "hasRecap" in s and "hasObsidian" in s


def test_generate_saves_session_has_artifacts_flags(sessions_api, tmp_path, monkeypatch, sync_threads):
    """Le flag hasBriefing/hasRecap/hasObsidian rispecchiano la presenza degli artefatti."""
    job = _make_ready_job(sessions_api, tmp_path, recap_md="# Recap presente", obsidian_note="# Nota presente")

    def fake_generate(j, store, answers, skipped, *, settings=None, provider=None, emit=None):
        return store.update(
            j.id,
            status="ready",
            briefing_md="# B",
            briefing_path="/x/b.md",
            recap_md="# Recap presente",
            obsidian_note="# Nota presente",
        )

    monkeypatch.setattr(sessions_api, "_generate_impl", fake_generate)
    sessions_api.generate(job.id, {}, [])

    sessions = sessions_api.list_sessions()
    assert len(sessions) == 1
    s = sessions[0]
    assert s["hasBriefing"] is True
    assert s["hasRecap"] is True
    assert s["hasObsidian"] is True


def test_open_session_returns_camelcase_artifacts(sessions_api, tmp_path, monkeypatch, sync_threads):
    """open_session(id) ritorna le chiavi camelCase con recapMd e obsidianNote."""
    job = _make_ready_job(sessions_api, tmp_path, recap_md="# Recap", obsidian_note="# Nota")

    def fake_generate(j, store, answers, skipped, *, settings=None, provider=None, emit=None):
        return store.update(
            j.id, status="ready", briefing_md="# B", briefing_path="/x/b.md", recap_md="# Recap", obsidian_note="# Nota"
        )

    monkeypatch.setattr(sessions_api, "_generate_impl", fake_generate)
    sessions_api.generate(job.id, {}, [])

    result = sessions_api.open_session(job.id)
    assert result is not None
    assert "briefingMd" in result
    assert "recapMd" in result
    assert "obsidianNote" in result
    assert result["recapMd"] == "# Recap"
    assert result["obsidianNote"] == "# Nota"


def test_open_session_not_found_returns_none(sessions_api):
    """open_session con id inesistente ritorna None."""
    result = sessions_api.open_session("nonexistent-id")
    assert result is None


def test_list_sessions_camelcase_shape(sessions_api, tmp_path, monkeypatch, sync_threads):
    """list_sessions ritorna dict con tutte le chiavi camelCase attese."""
    job = _make_ready_job(sessions_api, tmp_path)

    def fake_generate(j, store, answers, skipped, *, settings=None, provider=None, emit=None):
        return store.update(
            j.id, status="ready", briefing_md="# B", briefing_path="/x/b.md", recap_md="# R", obsidian_note="# N"
        )

    monkeypatch.setattr(sessions_api, "_generate_impl", fake_generate)
    sessions_api.generate(job.id, {}, [])

    sessions = sessions_api.list_sessions()
    assert sessions  # almeno uno
    s = sessions[0]
    for key in (
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
    ):
        assert key in s, f"chiave mancante: {key}"


def test_session_list_item_clar_count_counts_markers():
    """S1: clarCount conta i marcatori [DA CHIARIRE nel briefing salvato (chip "? N" in lista)."""
    from app.api import _session_list_item

    from vokari.store.session import Session

    briefing = (
        "# Briefing\n\n[DA CHIARIRE: Budget 700 o 730? (domanda saltata in rifinitura)]\n"
        "testo\n[DA CHIARIRE: Scadenza turni? (domanda saltata in rifinitura)]\n"
    )
    s = Session(
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
        artifacts={"briefing_md": briefing},
    )
    assert _session_list_item(s)["clarCount"] == 2
    # nessun marcatore → 0 (briefing completo)
    s2 = Session(
        id="s2",
        title="T2",
        created_at="2026-06-10T00:00:00",
        mode="solo",
        source="mic",
        model="small",
        language="it",
        duration_ms=1000,
        transcript="x",
        word_count=1,
        status="ready",
        artifacts={"briefing_md": "# Briefing pulito"},
    )
    assert _session_list_item(s2)["clarCount"] == 0


def test_session_list_item_has_audio_only_if_file_exists(tmp_path):
    """S2: hasAudio è True solo se il file audio locale esiste ancora (per gli import il path può
    essere stato spostato/cancellato → niente bottone Riproduci fantasma)."""
    from app.api import _session_list_item

    from vokari.store.session import Session

    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    base = {
        "title": "T",
        "created_at": "2026-06-10T00:00:00",
        "mode": "solo",
        "source": "mic",
        "model": "small",
        "language": "it",
        "duration_ms": 1000,
        "transcript": "x",
        "word_count": 1,
        "status": "ready",
        "artifacts": {},
    }
    assert _session_list_item(Session(id="s1", audio_path=str(wav), **base))["hasAudio"] is True
    assert _session_list_item(Session(id="s2", audio_path=str(tmp_path / "manca.wav"), **base))["hasAudio"] is False
    assert _session_list_item(Session(id="s3", audio_path="", **base))["hasAudio"] is False


def test_question_view_maps_camelcase_and_defaults():
    """I1+I2: _question_view espone why e mappa from_audio→fromAudio; campi assenti → default."""
    from app.api import _question_view

    v = _question_view(
        {"id": "q1", "text": "T", "priority": "high", "suggestions": ["a"], "why": "perché", "from_audio": True}
    )
    assert v["fromAudio"] is True and v["why"] == "perché"
    assert set(v.keys()) == {"id", "text", "priority", "suggestions", "why", "fromAudio"}
    v2 = _question_view({"id": "q2", "text": "T2", "priority": "low"})
    assert v2["fromAudio"] is False and v2["why"] == "" and v2["suggestions"] == []


def test_get_questions_returns_camelcase_view(tmp_path):
    """get_questions ritorna la shape camelCase (fromAudio), non il model_dump snake."""
    from app.api import Api
    from app.jobs import Job, JobStore

    from vokari.store.sessions_repo import SessionsRepo

    api = Api(store=JobStore(jobs_dir=str(tmp_path / "j")), sessions=SessionsRepo(sessions_dir=str(tmp_path / "s")))
    job = api._store.create(Job.new("/x.wav"))
    api._store.update(job.id, questions=[{"id": "q1", "text": "T", "priority": "high", "why": "w", "from_audio": True}])
    out = api.get_questions(job.id)
    assert out and out[0]["fromAudio"] is True and "from_audio" not in out[0]


def test_api_delete_api_key(api, tmp_path, monkeypatch):
    """SET2: delete_api_key svuota il keyring e riporta hasApiKey a False."""
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    api.set_api_key("sk-ant-x")
    assert api.get_settings()["hasApiKey"] is True
    assert api.delete_api_key() == {"ok": True, "hasApiKey": False}
    assert api.get_settings()["hasApiKey"] is False


def test_api_verify_api_key_no_key(api, tmp_path, monkeypatch):
    """SET1: senza chiave impostata → ok:False, reachable:False (niente chiamata di rete)."""
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    res = api.verify_api_key()
    assert res["ok"] is False and res["reachable"] is False


def test_api_verify_api_key_ok(api, tmp_path, monkeypatch):
    """SET1: con chiave + Claude che risponde al ping minimale → ok:True, reachable:True."""
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    api.set_api_key("sk-ant-x")
    import anthropic

    class _Msgs:
        def create(self, **kw):
            return object()

    class _Client:
        def __init__(self, **kw):
            self.messages = _Msgs()

    monkeypatch.setattr(anthropic, "Anthropic", _Client)
    res = api.verify_api_key()
    assert res["ok"] is True and res["reachable"] is True


def test_play_session_audio_handles_missing(tmp_path, monkeypatch):
    """S2: play_session_audio ritorna {ok:False} se la sessione non esiste, non ha audio o il
    file è sparito; apre il lettore (os.startfile) e ritorna {ok:True} quando il file c'è."""
    from app.api import Api
    from app.jobs import JobStore

    from vokari.store.session import Session
    from vokari.store.sessions_repo import SessionsRepo

    api = Api(
        store=JobStore(jobs_dir=str(tmp_path / "jobs")), sessions=SessionsRepo(sessions_dir=str(tmp_path / "ses"))
    )
    assert api.play_session_audio("inesistente")["ok"] is False

    wav = tmp_path / "ok.wav"
    wav.write_bytes(b"RIFF")
    sess = Session(
        id="sA",
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
        audio_path=str(wav),
    )
    api._sessions.save(sess)
    opened: dict = {}
    monkeypatch.setattr("app.api.os.startfile", lambda p: opened.update(path=p), raising=False)
    res = api.play_session_audio("sA")
    assert res["ok"] is True and opened["path"] == str(wav)

    # sessione con audio_path che non esiste più → ok:False, niente apertura
    sess.audio_path = str(tmp_path / "sparito.wav")
    api._sessions.save(sess)
    assert api.play_session_audio("sA")["ok"] is False


def test_search_sessions_filtra_per_query(sessions_api, tmp_path, monkeypatch, sync_threads):
    """search_sessions con query matching ritorna la sessione; query non matching = vuota."""
    job = _make_ready_job(sessions_api, tmp_path)

    def fake_generate(j, store, answers, skipped, *, settings=None, provider=None, emit=None):
        return store.update(
            j.id, status="ready", briefing_md="# B", briefing_path="/x/b.md", recap_md="# R", obsidian_note="# N"
        )

    monkeypatch.setattr(sessions_api, "_generate_impl", fake_generate)
    sessions_api.generate(job.id, {}, [])

    results_hit = sessions_api.search_sessions("Test sessione")
    assert len(results_hit) == 1

    results_miss = sessions_api.search_sessions("nessunrisultato_xyz_999")
    assert len(results_miss) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Task 12 — cancel_recording elimina il WAV temporaneo
# ─────────────────────────────────────────────────────────────────────────────


def test_cancel_recording_deletes_wav_if_written(isolated_api, tmp_path):
    """cancel_recording elimina il WAV scritto da Recorder.stop() se esiste."""
    wav_path = str(tmp_path / "rec-test.wav")
    Path(wav_path).write_bytes(b"RIFF")

    class _FakeRecWithWav:
        def start(self):
            pass

        def stop(self):
            return type(
                "R",
                (),
                {
                    "wav_path": wav_path,
                    "warnings": [],
                    "diagnostics": {},
                },
            )()

    isolated_api._rec = _FakeRecWithWav()
    isolated_api.cancel_recording()

    assert not Path(wav_path).exists(), "Il WAV deve essere eliminato dopo cancel_recording"


def test_delete_session_removes_from_library(sessions_api, tmp_path, monkeypatch, sync_threads):
    """delete_session rimuove la sessione dalla libreria (e il job persistito) (FB-D)."""
    job = _make_ready_job(sessions_api, tmp_path)

    def fake_generate(j, store, answers, skipped, *, settings=None, provider=None, emit=None):
        return store.update(
            j.id, status="ready", briefing_md="# B", briefing_path="/x/b.md", recap_md="# R", obsidian_note="# N"
        )

    monkeypatch.setattr(sessions_api, "_generate_impl", fake_generate)
    sessions_api.generate(job.id, {}, [])
    assert any(x["id"] == job.id for x in sessions_api.list_sessions())

    res = sessions_api.delete_session(job.id)
    assert res["ok"] is True
    assert sessions_api._sessions.get(job.id) is None
    assert not any(x["id"] == job.id for x in sessions_api.list_sessions())
    assert sessions_api._store.get(job.id) is None  # anche il job persistito è rimosso


def test_delete_session_missing_returns_false(sessions_api):
    assert sessions_api.delete_session("non-esiste")["ok"] is False


def test_delete_sessions_batch(tmp_path, monkeypatch):
    """delete_sessions elimina più sessioni in un colpo; gli id inesistenti sono ignorati."""
    from datetime import UTC, datetime

    from app.api import Api
    from app.jobs import JobStore

    from vokari.store.session import Session
    from vokari.store.sessions_repo import SessionsRepo

    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    repo = SessionsRepo(sessions_dir=tmp_path / "sessions")
    api = Api(store=JobStore(jobs_dir=tmp_path / "jobs"), sessions=repo)

    for sid in ("a", "b", "c"):
        repo.save(
            Session(
                id=sid,
                title=f"Sessione {sid}",
                created_at=datetime.now(UTC).isoformat(),
                status="ready",
            )
        )

    res = api.delete_sessions(["a", "c", "zzz"])
    assert res["ok"] is True
    assert res["deleted"] == 2
    remaining = {s.id for s in repo.list_all()}
    assert remaining == {"b"}


def test_list_models_includes_description(isolated_api):
    """Ogni modello espone una descrizione non vuota per la UI (FB-D)."""
    models = isolated_api.list_models()
    assert models and all("description" in m for m in models)
    rec = [m for m in models if m["recommended"]]
    assert rec and rec[0]["description"]


def test_list_ollama_models_includes_card_metadata(isolated_api, monkeypatch):
    """Ogni modello del catalogo Ollama espone i metadati 'scheda modello' per la UI:
    speed/quality (meter 0..3), params, context, tags, detailUrl — oltre a description."""
    import vokari.llm.ollama_provider as op

    # Niente server Ollama → list_ollama_models ritorna solo il catalogo curato (deterministico).
    monkeypatch.setattr(op, "is_up", lambda endpoint: False)

    models = isolated_api.list_ollama_models()
    assert models, "il catalogo curato non deve essere vuoto"
    for m in models:
        for key in ("speed", "quality", "params", "context", "tags", "detailUrl"):
            assert key in m, f"manca '{key}' nella voce {m['name']}"
        assert m["detailUrl"].startswith("https://ollama.com/library/")
        assert isinstance(m["tags"], list)
    # le voci curate (recommended) hanno specs valorizzate e meter nel range atteso
    rec = [m for m in models if m["recommended"]]
    assert rec
    assert all(0 <= m["speed"] <= 3 and 0 <= m["quality"] <= 3 for m in rec)
    assert all(m["params"] and m["tags"] and m["description"] for m in rec)


def test_probe_audio_returns_duration_and_size(api, tmp_path, monkeypatch):
    """MDL2: probe_audio ritorna durationS (ffprobe) e sizeBytes (getsize)."""
    from vokari.audio import convert as convert_mod

    monkeypatch.setattr(convert_mod, "probe_duration_s", lambda p: 12.5)
    f = tmp_path / "a.m4a"
    f.write_bytes(b"x" * 2048)
    assert api.probe_audio(str(f)) == {"durationS": 12.5, "sizeBytes": 2048}


def test_probe_audio_missing_file_is_safe(api, monkeypatch):
    """MDL2: file inesistente / ffprobe muto → 0/0 (niente durata/peso inventati)."""
    from vokari.audio import convert as convert_mod

    monkeypatch.setattr(convert_mod, "probe_duration_s", lambda p: None)
    assert api.probe_audio("/non/esiste.m4a") == {"durationS": 0.0, "sizeBytes": 0}


def test_min_ram_gb_from_size_label():
    """MOD2: la RAM minima stimata scala con la dimensione su disco; ignota (no GB) → 0."""
    from app.api import _min_ram_gb

    assert _min_ram_gb("~4.7 GB") == round(4.7 * 1.3, 1)
    assert _min_ram_gb("9.0 GB") == round(9.0 * 1.3, 1)
    assert _min_ram_gb("?") == 0.0
    assert _min_ram_gb("466 MB") == 0.0  # solo le dimensioni in GB hanno una stima (i briefing-model sono GB)


def test_system_specs_exposes_ram_total(api):
    """MOD2: system_specs espone ramTotalGb (RAM totale, GB) per i suggerimenti di compatibilità."""
    specs = api.system_specs()
    assert "ramTotalGb" in specs
    assert isinstance(specs["ramTotalGb"], (int, float))
    assert specs["ramTotalGb"] >= 0


def test_list_ollama_models_includes_min_ram(isolated_api, monkeypatch):
    """MOD2: ogni voce Ollama espone minRamGb; il 14B stima più RAM del 7B."""
    import vokari.llm.ollama_provider as op

    monkeypatch.setattr(op, "is_up", lambda endpoint: False)
    models = isolated_api.list_ollama_models()
    assert models
    assert all("minRamGb" in m and isinstance(m["minRamGb"], (int, float)) for m in models)
    by_name = {m["name"]: m for m in models}
    assert by_name["qwen2.5:14b"]["minRamGb"] > by_name["qwen2.5:7b"]["minRamGb"]


def test_disk_usage_returns_used_and_free(isolated_api, monkeypatch):
    """MOD3: disk_usage espone usedByModelsGb e freeGb (numerici, free >= 0)."""
    from vokari.llm import ollama_provider as op

    monkeypatch.setattr(op, "is_up", lambda endpoint: False)  # niente Ollama → solo Whisper
    du = isolated_api.disk_usage()
    assert set(du) == {"usedByModelsGb", "freeGb"}
    assert isinstance(du["usedByModelsGb"], (int, float))
    assert isinstance(du["freeGb"], (int, float))
    assert du["freeGb"] >= 0


def test_disk_usage_includes_ollama_bytes(isolated_api, monkeypatch):
    """MOD3: usedByModelsGb somma anche i byte dei modelli Ollama installati (via /api/tags)."""
    import httpx

    from vokari.llm import ollama_provider as op

    monkeypatch.setattr(op, "is_up", lambda endpoint: True)

    class _R:
        status_code = 200

        def json(self):
            return {"models": [{"name": "qwen2.5:7b", "size": 5_000_000_000}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _R())
    du = isolated_api.disk_usage()
    assert du["usedByModelsGb"] >= 5.0  # ~5 GB di Ollama inclusi


def test_cancel_ollama_pull_sets_flag(api):
    """MOD1: cancel_ollama_pull registra il nome tra i pull da interrompere e ritorna ok."""
    assert api.cancel_ollama_pull("qwen2.5:7b") == {"ok": True}
    assert "qwen2.5:7b" in api._ollama_pull_cancel


def test_pull_ollama_model_honors_cancel(api, monkeypatch, tmp_path):
    """MOD1: una richiesta di annullamento a metà pull chiude lo stream ed emette
    `ollama_pull status=cancelled` (mai `done`); il flag viene ripulito. Stream HTTP mockato."""
    import json as _json

    import app.api as apimod
    import httpx

    from vokari.llm import ollama_provider as op

    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    monkeypatch.setattr(op, "is_up", lambda endpoint: True)

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(api, "_emit", lambda ev, p: events.append((ev, p)))
    # thread sincrono → _do_pull gira subito dentro pull_ollama_model
    monkeypatch.setattr(
        apimod.threading, "Thread", lambda target, daemon=None: type("T", (), {"start": staticmethod(target)})()
    )

    name = "qwen2.5:7b"

    class _FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            pass

        def iter_lines(self):
            yield _json.dumps({"total": 100, "completed": 10})
            api.cancel_ollama_pull(name)  # annullamento richiesto a metà download
            yield _json.dumps({"total": 100, "completed": 20})  # questa iterazione vede il flag

    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _FakeStream())

    api.pull_ollama_model(name)

    statuses = [p["status"] for ev, p in events if ev == "ollama_pull"]
    assert "cancelled" in statuses
    assert "done" not in statuses
    assert name not in api._ollama_pull_cancel  # flag ripulito dopo l'annullamento


def test_ollama_status_reports_runtime_state(isolated_api, monkeypatch):
    """ollama_status espone installed/running/bundled/canInstall/endpoint per la UI
    (gestione avvio/installazione automatici di Ollama)."""
    import app.ollama_manager as om

    monkeypatch.setattr(om, "is_installed", lambda d: True)
    monkeypatch.setattr(om, "is_running", lambda e: False)
    monkeypatch.setattr(om, "can_auto_install", lambda: True)
    monkeypatch.setattr(om, "bundled_exe", lambda d: Path("does-not-exist"))

    st = isolated_api.ollama_status()
    assert set(st) >= {"installed", "running", "bundled", "canInstall", "endpoint"}
    assert st["installed"] is True
    assert st["running"] is False
    assert st["canInstall"] is True
    assert st["bundled"] is False
    assert isinstance(st["endpoint"], str)


# ─────────────────────────────────────────────────────────────────────────────
# M7-H — Artefatti: get_artifacts espone recapMd/obsidianNote; export_pdf/obsidian
# ─────────────────────────────────────────────────────────────────────────────


def test_get_artifacts_exposes_recap_and_obsidian(sessions_api, tmp_path):
    """get_artifacts espone recapMd e obsidianNote valorizzati dal job."""
    from app.jobs import Job

    audio = str(tmp_path / "b.wav")
    Path(audio).touch()
    job = sessions_api._store.create(Job.new(audio, mode="solo"))
    sessions_api._store.update(
        job.id,
        transcript="t",
        duration_s=60.0,
        briefing_md="# B",
        briefing_path="/x/b.md",
        recap_md="# Recap reale",
        obsidian_note="# Nota reale",
        status="ready",
    )
    result = sessions_api.get_artifacts(job.id)
    assert result is not None
    assert result["recapMd"] == "# Recap reale"
    assert result["obsidianNote"] == "# Nota reale"


def test_export_pdf_creates_file(sessions_api, tmp_path, monkeypatch):
    """export_pdf genera un PDF su disco e ritorna ok=True e il path."""
    from app.jobs import Job

    audio = str(tmp_path / "c.wav")
    Path(audio).touch()
    job = sessions_api._store.create(Job.new(audio, mode="solo", title="Riunione PDF"))
    sessions_api._store.update(
        job.id,
        recap_md="# Recap PDF\n\nTesto.",
        status="ready",
        briefing_md="# B",
        briefing_path=str(tmp_path / "b.md"),
    )

    # briefing_dir punta a tmp_path cosi il PDF viene scritto li
    import vokari.settings as sm

    monkeypatch.setattr(sm, "load", lambda: sm.Settings(briefing_dir=str(tmp_path)))

    result = sessions_api.export_pdf(job.id)
    assert result["ok"] is True
    assert "path" in result
    assert Path(result["path"]).exists()
    assert Path(result["path"]).stat().st_size > 0


def test_save_text_file_writes_content(sessions_api, tmp_path, monkeypatch):
    """save_text_file scrive il contenuto sul path scelto (FB-C). Senza dialog nativo
    (FakeWindow) ricade su briefing_dir."""
    import vokari.settings as sm

    monkeypatch.setattr(sm, "load", lambda: sm.Settings(briefing_dir=str(tmp_path)))
    result = sessions_api.save_text_file("# Briefing\n\ncorpo", "briefing.md")
    assert result["ok"] is True
    assert Path(result["path"]).exists()
    assert Path(result["path"]).read_text(encoding="utf-8") == "# Briefing\n\ncorpo"


def test_export_pdf_returns_error_on_bad_job(sessions_api):
    """export_pdf con job inesistente ritorna ok=False con messaggio di errore."""
    result = sessions_api.export_pdf("nonexistent-id")
    assert result["ok"] is False
    assert "error" in result


def test_export_obsidian_without_vault_returns_error(sessions_api, tmp_path, monkeypatch):
    """export_obsidian senza vault configurato ritorna ok=False con errore leggibile."""
    from app.jobs import Job

    import vokari.settings as sm

    audio = str(tmp_path / "d.wav")
    Path(audio).touch()
    job = sessions_api._store.create(Job.new(audio, mode="solo"))
    sessions_api._store.update(
        job.id,
        analysis={
            "meta": {"type": "solo", "title": "T", "date": "2026-06-08", "participants": [], "duration_min": 1},
            "context": "ctx",
            "key_ideas": [],
            "decisions": [],
            "next_steps": [],
            "open_questions": [],
            "entities": [],
        },
        status="ready",
    )

    monkeypatch.setattr(sm, "load", lambda: sm.Settings(obsidian_vault=""))  # vault vuoto

    result = sessions_api.export_obsidian(job.id)
    assert result["ok"] is False
    assert "vault" in result.get("error", "").lower() or "obsidian" in result.get("error", "").lower()


def test_export_obsidian_with_vault_writes_files(sessions_api, tmp_path, monkeypatch):
    """export_obsidian con vault configurato scrive le note su disco."""
    from app.jobs import Job

    import vokari.settings as sm

    vault = tmp_path / "vault"
    vault.mkdir()

    audio = str(tmp_path / "e.wav")
    Path(audio).touch()
    job = sessions_api._store.create(Job.new(audio, mode="solo", title="Sessione Obsidian"))
    sessions_api._store.update(
        job.id,
        analysis={
            "meta": {
                "type": "solo",
                "title": "Sessione Obsidian",
                "date": "2026-06-08",
                "participants": [],
                "duration_min": 5,
            },
            "context": "Contesto test",
            "key_ideas": ["idea 1"],
            "decisions": [],
            "next_steps": [],
            "open_questions": [],
            "entities": [],
        },
        status="ready",
    )

    monkeypatch.setattr(sm, "load", lambda: sm.Settings(obsidian_vault=str(vault)))

    result = sessions_api.export_obsidian(job.id)
    assert result["ok"] is True
    assert result["count"] >= 1
    assert len(result["paths"]) >= 1
    for p in result["paths"]:
        assert Path(p).exists()


# ─────────────────────────────────────────────────────────────────────────────
# M7-D — Annulla / Pausa / Riprendi registrazione
# ─────────────────────────────────────────────────────────────────────────────


def test_pause_resume_cancel_recording(api):
    assert api.pause_recording()["ok"] is False  # nessuna registrazione attiva
    assert api.cancel_recording()["ok"] is False

    class FakeRec:
        def __init__(self):
            self.paused = False
            self.stopped = False

        def pause(self):
            self.paused = True

        def resume(self):
            self.paused = False

        def stop(self):
            self.stopped = True

    rec = FakeRec()
    api._rec = rec
    assert api.pause_recording() == {"ok": True, "paused": True}
    assert rec.paused is True
    assert api.resume_recording() == {"ok": True, "paused": False}
    assert rec.paused is False
    assert api.cancel_recording()["ok"] is True
    assert rec.stopped is True
    assert api._rec is None


# ─────────────────────────────────────────────────────────────────────────────
# WP2 (F2) — Apertura sessione dalla libreria: briefingPath + export PDF/Obsidian
# Scenario reale: una Session salvata E il Job corrispondente persistito (stesso id).
# ─────────────────────────────────────────────────────────────────────────────


def _make_persisted_session(api, tmp_path, *, vault_briefing=True):
    """Crea un Job persistito su disco + salva la Session corrispondente (session.id == job.id).
    Riproduce lo stato post-run: in Sessioni clicco una riga → open_session(id)."""
    from app.jobs import Job

    audio = str(tmp_path / "wp2.wav")
    Path(audio).touch()
    briefing_path = str(tmp_path / "briefing" / "out.md")
    job = api._store.create(Job.new(audio, mode="solo", title="Sessione WP2", model="large-v3-turbo", language="it"))
    api._store.update(
        job.id,
        transcript="trascrizione wp2",
        duration_s=90.0,
        analysis={
            "meta": {
                "type": "solo",
                "title": "Sessione WP2",
                "date": "2026-06-09",
                "participants": [],
                "duration_min": 2,
            },
            "context": "Contesto WP2",
            "key_ideas": ["idea wp2"],
            "decisions": [],
            "next_steps": [],
            "open_questions": [],
            "entities": [],
        },
        questions=[],
        briefing_md="# Briefing WP2",
        briefing_path=briefing_path,
        recap_md="# Recap WP2\n\nTesto recap.",
        obsidian_note="# Nota WP2",
        status="ready",
    )
    job = api._store.get(job.id)
    api._save_session(job)  # persiste la Session con lo stesso id
    return job, briefing_path


def test_open_session_returns_briefing_path_from_persisted_job(sessions_api, tmp_path):
    """open_session(id) deve restituire il briefingPath reale del job persistito (non vuoto),
    così 'Apri cartella' nel frontend parte."""
    job, briefing_path = _make_persisted_session(sessions_api, tmp_path)
    result = sessions_api.open_session(job.id)
    assert result is not None
    assert result["briefingPath"] == briefing_path
    assert result["briefingPath"]  # non vuoto


def test_open_session_briefing_path_empty_when_no_job(sessions_api, tmp_path):
    """Se la Session esiste ma il Job non è più su disco, briefingPath resta '' (no crash)."""
    from datetime import UTC, datetime

    from vokari.store.session import Session

    sessions_api._sessions.save(
        Session(
            id="orphan-session",
            title="Senza job",
            created_at=datetime.now(UTC).isoformat(),
            mode="solo",
            artifacts={"briefing_md": "# B", "recap_md": "# R", "obsidian_note": "# N"},
        )
    )
    result = sessions_api.open_session("orphan-session")
    assert result is not None
    assert result["briefingPath"] == ""


def test_export_pdf_from_opened_session_creates_pdf(sessions_api, tmp_path, monkeypatch):
    """export_pdf(sessionId) sul job persistito genera un PDF reale (header %PDF-)."""
    job, _ = _make_persisted_session(sessions_api, tmp_path)
    import vokari.settings as sm

    monkeypatch.setattr(sm, "load", lambda: sm.Settings(briefing_dir=str(tmp_path / "out")))

    result = sessions_api.export_pdf(job.id)
    assert result["ok"] is True
    p = Path(result["path"])
    assert p.exists()
    assert p.read_bytes()[:5] == b"%PDF-"


def test_export_obsidian_from_opened_session_writes_note(sessions_api, tmp_path, monkeypatch):
    """export_obsidian(sessionId) sul job persistito scrive almeno una nota .md nel vault."""
    job, _ = _make_persisted_session(sessions_api, tmp_path)
    vault = tmp_path / "vault"
    import vokari.settings as sm

    monkeypatch.setattr(sm, "load", lambda: sm.Settings(obsidian_vault=str(vault)))

    result = sessions_api.export_obsidian(job.id)
    assert result["ok"] is True
    assert result["count"] >= 1
    mds = list(vault.glob("*.md"))
    assert len(mds) >= 1


def test_export_pdf_fallback_to_session_when_job_missing(sessions_api, tmp_path, monkeypatch):
    """Fallback: se il job non è su disco ma la Session sì, export_pdf usa il recap_md della Session."""
    from datetime import UTC, datetime

    from vokari.store.session import Session

    sessions_api._sessions.save(
        Session(
            id="orphan-pdf",
            title="Solo sessione",
            created_at=datetime.now(UTC).isoformat(),
            mode="solo",
            audio_path=str(tmp_path / "x.wav"),
            artifacts={"recap_md": "# Recap orfano\n\nTesto.", "briefing_md": "# B", "obsidian_note": "# N"},
        )
    )
    import vokari.settings as sm

    monkeypatch.setattr(sm, "load", lambda: sm.Settings(briefing_dir=str(tmp_path / "out2")))

    result = sessions_api.export_pdf("orphan-pdf")
    assert result["ok"] is True
    assert Path(result["path"]).read_bytes()[:5] == b"%PDF-"


def test_export_obsidian_fallback_to_session_when_job_missing(sessions_api, tmp_path, monkeypatch):
    """Fallback: senza job, export_obsidian scrive la singola nota già renderizzata della Session."""
    from datetime import UTC, datetime

    from vokari.store.session import Session

    sessions_api._sessions.save(
        Session(
            id="orphan-obs",
            title="Sessione orfana",
            created_at=datetime.now(UTC).isoformat(),
            mode="solo",
            artifacts={"recap_md": "# R", "briefing_md": "# B", "obsidian_note": "# Nota orfana\n\nContenuto."},
        )
    )
    vault = tmp_path / "vault2"
    import vokari.settings as sm

    monkeypatch.setattr(sm, "load", lambda: sm.Settings(obsidian_vault=str(vault)))

    result = sessions_api.export_obsidian("orphan-obs")
    assert result["ok"] is True
    assert result["count"] == 1
    assert len(list(vault.glob("*.md"))) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Task 12 — LiveTranscriber cablato in start_recording
# ─────────────────────────────────────────────────────────────────────────────


def test_start_recording_wires_live_transcriber(tmp_path, monkeypatch):
    """Con live_preview=True, start_recording deve passare on_audio!=None al Recorder."""
    from app.api import Api
    from app.jobs import JobStore

    from vokari import settings as settings_mod
    from vokari.audio import capture

    captured = {}

    class _FakeRec:
        def __init__(self, source, wav, *, device=None, on_level=None, on_audio=None):
            captured["on_audio"] = on_audio

        def start(self):
            pass

    monkeypatch.setattr(capture, "Recorder", _FakeRec)
    s = settings_mod.load()
    s.live_preview = True
    monkeypatch.setattr(settings_mod, "load", lambda: s)

    api = Api(store=JobStore(jobs_dir=str(tmp_path / "jobs")))
    api.start_recording("mic")
    assert captured["on_audio"] is not None, "on_audio non cablato con live_preview attivo"
    # cleanup: il thread del LiveTranscriber è daemon ma fermiamolo esplicitamente
    if api._live is not None:
        api._live.stop()


def test_start_recording_no_live_when_disabled(tmp_path, monkeypatch):
    """Con live_preview=False, on_audio deve essere None (nessun LiveTranscriber creato)."""
    from app.api import Api
    from app.jobs import JobStore

    from vokari import settings as settings_mod
    from vokari.audio import capture

    captured = {}

    class _FakeRec:
        def __init__(self, source, wav, *, device=None, on_level=None, on_audio=None):
            captured["on_audio"] = on_audio

        def start(self):
            pass

    monkeypatch.setattr(capture, "Recorder", _FakeRec)
    s = settings_mod.load()
    s.live_preview = False
    monkeypatch.setattr(settings_mod, "load", lambda: s)

    api = Api(store=JobStore(jobs_dir=str(tmp_path / "jobs")))
    api.start_recording("mic")
    assert captured["on_audio"] is None, "on_audio deve essere None con live_preview disattivo"
    assert api._live is None, "_live deve essere None con live_preview disattivo"


def _wait_until(predicate, timeout=5.0, step=0.02):
    """Attende che `predicate()` diventi vero, fino a `timeout` secondi.

    I test del monitor risorse NON devono assumere un tempo fisso per il primo emit: il
    primo tick scandisce tutti i processi (`psutil.process_iter`) e sotto carico CPU può
    tardare oltre i ~150ms. Attendere la CONDIZIONE (con poll frequente) li rende
    deterministici a prescindere dal carico — invece di un `time.sleep` a finestra stretta.
    """
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


def test_shutdown_silences_emit_and_stops_resource_monitor(tmp_path):
    """Alla chiusura: _window=None (emit no-op) e il monitor risorse smette di emettere."""
    import time

    from app.api import Api
    from app.jobs import JobStore

    class _FakeWin:
        def __init__(self):
            self.calls = []

        def evaluate_js(self, js):
            self.calls.append(js)

    api = Api(store=JobStore(jobs_dir=str(tmp_path / "jobs")))
    fw = _FakeWin()
    api._window = fw
    api.start_resource_monitor(interval=0.05)
    # poll-until invece di sleep fisso: attende il primo emit a prescindere dal carico CPU
    assert _wait_until(lambda: any("resource_usage" in c for c in fw.calls)), (
        "il monitor doveva emettere prima dello shutdown"
    )

    api.shutdown()
    assert api._window is None
    n = len(fw.calls)
    # Dopo shutdown _emit è no-op (_window=None) e il loop esce: nessun nuovo emit.
    # L'attesa è conservativa (il carico può solo ridurre gli emit, mai aumentarli a finestra None).
    time.sleep(0.2)
    assert len(fw.calls) == n, "dopo shutdown il monitor non deve più emettere"


def test_resource_monitor_restartable_after_shutdown(tmp_path):
    """start_resource_monitor è ri-avviabile dopo uno shutdown (Event ri-armato)."""
    from app.api import Api
    from app.jobs import JobStore

    class _FakeWin:
        def __init__(self):
            self.calls = []

        def evaluate_js(self, js):
            self.calls.append(js)

    api = Api(store=JobStore(jobs_dir=str(tmp_path / "jobs")))
    api._window = _FakeWin()
    api.start_resource_monitor(interval=0.05)
    api.shutdown()
    # Attende che il vecchio thread sia effettivamente terminato prima di riavviare: altrimenti
    # il guard `is_alive()` in start_resource_monitor potrebbe saltare l'avvio (race sotto carico).
    assert _wait_until(lambda: not (api._res_thread and api._res_thread.is_alive())), (
        "il thread del monitor doveva terminare dopo shutdown"
    )
    # riavvio (es. nuova finestra/embedding): deve tornare a emettere
    fw2 = _FakeWin()
    api._window = fw2
    api.start_resource_monitor(interval=0.05)
    assert _wait_until(lambda: any("resource_usage" in c for c in fw2.calls)), "il monitor deve ripartire dopo shutdown"
    api.shutdown()


# ─────────────────────────────────────────────────────────────────────────────
# Task 13 — resume_job guard: audio_path vuoto o file mancante → status error
# ─────────────────────────────────────────────────────────────────────────────


def test_resume_job_with_empty_audio_path_returns_error_status(tmp_path, monkeypatch):
    """resume_job con audio_path vuoto → status error (non crash in pipeline)."""
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    api = Api(store=JobStore(jobs_dir=tmp_path / "jobs"))
    job = api._store.create(Job.new("", title="T", status="transcribing"))
    result = api.resume_job(job.id)
    assert result is not None
    assert result["status"] == "error", f"deve essere error, trovato: {result['status']}"
    assert result["error"]  # messaggio non vuoto


def test_resume_job_with_missing_file_returns_error_status(tmp_path, monkeypatch):
    """resume_job con audio_path che punta a file inesistente → status error."""
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    api = Api(store=JobStore(jobs_dir=tmp_path / "jobs"))
    job = api._store.create(Job.new("/nonexistente/audio.wav", title="T", status="transcribing"))
    result = api.resume_job(job.id)
    assert result is not None
    assert result["status"] == "error"


def test_happy_path_import_to_session_real_seams(tmp_path, monkeypatch):
    """PATH FELICE end-to-end senza mockare la pipeline (rete anti-regressione ADR-010: i
    test mockati nascosero un path felice rotto). Whisper è mockato SOLO al livello modello e
    il provider è stubbato, ma trascrizione→analisi→render→briefing.md su disco e Session
    salvata sono REALI."""
    import app.api as apimod
    from app.api import Api
    from app.jobs import JobStore

    from vokari.analyze.schema import Analysis, Meta
    from vokari.audio import capture
    from vokari.store.sessions_repo import SessionsRepo
    from vokari.transcribe import whisper as whisper_mod

    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))

    # WAV reale 16k mono → _is_wav_16k_mono True → niente ffmpeg
    wav = tmp_path / "audio.wav"
    capture.write_pcm16_wav([0] * 16000, wav, samplerate=16000, channels=1)

    # FakeModel: nessun faster-whisper reale
    class _Seg:
        def __init__(self, text):
            self.start, self.end, self.text = 0.0, 1.0, text

    class _FakeModel:
        def transcribe(self, audio, language=None, beam_size=5, **_):
            return ([_Seg("ciao questo e un test reale")], object())

    monkeypatch.setattr(whisper_mod, "_load_model", lambda name: _FakeModel())

    # Provider stub via factory (no LLM reale) + 0 domande → genera subito il briefing
    class _Stub:
        def chat_json(self, system, user, *, json_schema=None):
            return Analysis(meta=Meta(type="solo", title="Test"), context="ctx", key_ideas=["idea"]).model_dump()

        def chat_text(self, system, user):
            return ""

    # pipeline.py importa make_provider per nome (from ... import) → patchare il nome
    # legato NEL modulo pipeline, non vokari.llm.factory.
    monkeypatch.setattr("app.pipeline.make_provider", lambda s: _Stub())
    monkeypatch.setattr(
        "vokari.analyze.interview.detect_questions", lambda a, t, *, provider, mode, should_cancel=None: []
    )
    # Il preflight (probe durata) usa subprocess/ffprobe; questo test patcha threading.Thread
    # globalmente (sotto) per girare sincrono → il subprocess interno andrebbe in conflitto.
    # Stub a None: il preflight è ortogonale ai seam trascrizione→analisi→briefing qui testati.
    monkeypatch.setattr("vokari.audio.convert.probe_duration_s", lambda path: None)

    # thread daemon eseguiti in modo sincrono
    monkeypatch.setattr(
        apimod.threading, "Thread", lambda target, daemon=None: type("T", (), {"start": staticmethod(target)})()
    )

    api = Api(
        store=JobStore(jobs_dir=str(tmp_path / "jobs")), sessions=SessionsRepo(sessions_dir=str(tmp_path / "sessions"))
    )
    out = api.import_file(str(wav), mode="solo", title="HappyPath")
    jid = out["jobId"]

    job = api._store.get(jid)
    assert job.status == "ready", f"atteso ready, ottenuto {job.status!r} ({job.error!r})"
    # artefatto REALE su disco (non un mock)
    assert job.briefing_path and Path(job.briefing_path).exists()
    assert "test" in Path(job.briefing_path).read_text(encoding="utf-8").lower()
    # Session REALMENTE salvata nella libreria
    sessions = api.list_sessions()
    assert len(sessions) == 1 and sessions[0]["id"] == jid


# ---------------------------------------------------------------------------
# Bug-T1 (C1): null guard on_audio callback (non-lambda, guard _live_inst)
# ---------------------------------------------------------------------------


def test_on_audio_is_named_function_not_lambda(tmp_path, monkeypatch):
    from app.api import Api
    from app.jobs import JobStore

    from vokari import settings as settings_mod
    from vokari.audio import capture

    captured = {}

    class _FakeRec:
        def __init__(self, source, wav, *, device=None, on_level=None, on_audio=None):
            captured["on_audio"] = on_audio

        def start(self):
            pass

    monkeypatch.setattr(capture, "Recorder", _FakeRec)
    s = settings_mod.load()
    s.live_preview = True
    s.live_model = "tiny"
    s.whisper_model = "large-v3-turbo"
    monkeypatch.setattr(settings_mod, "load", lambda: s)
    api = Api(store=JobStore(jobs_dir=str(tmp_path / "jobs")))
    api.start_recording("mic")
    if api._live is not None:
        api._live.stop()
    on_audio = captured.get("on_audio")
    assert on_audio is not None
    assert on_audio.__name__ != "<lambda>"


# ---------------------------------------------------------------------------
# Bug-T2 (I1): cancel_recording ferma Recorder PRIMA di LiveTranscriber
# ---------------------------------------------------------------------------


def test_cancel_recording_stops_recorder_before_live_transcriber(tmp_path):
    from app.api import Api
    from app.jobs import JobStore

    order = []

    class _FakeRec:
        def stop(self):
            order.append("rec")
            return type("R", (), {"wav_path": None, "warnings": [], "diagnostics": {}})()

    class _FakeLive:
        def stop(self):
            order.append("live")

    api = Api(store=JobStore(jobs_dir=str(tmp_path / "jobs")))
    api._rec = _FakeRec()
    api._live = _FakeLive()
    api.cancel_recording()
    assert order == ["rec", "live"]


# ---------------------------------------------------------------------------
# Bug-T4 (I3): Job.created_at registra avvio registrazione, non fine elaborazione
# ---------------------------------------------------------------------------


def test_save_session_uses_job_created_at_not_processing_time(tmp_path, monkeypatch):
    from app.api import Api
    from app.jobs import Job, JobStore

    from vokari.store.sessions_repo import SessionsRepo

    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    api = Api(
        store=JobStore(jobs_dir=str(tmp_path / "jobs")), sessions=SessionsRepo(sessions_dir=str(tmp_path / "sessions"))
    )
    fixed_ts = "2026-01-15T10:00:00+00:00"
    job = api._store.create(
        Job.new(
            "/tmp/x.wav",
            title="timing test",
            transcript="contenuto valido",
            duration_s=30.0,
            status="ready",
            created_at=fixed_ts,
        )
    )
    api._save_session(job)
    sessions = api.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["createdAt"] == fixed_ts
