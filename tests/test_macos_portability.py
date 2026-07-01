"""Portabilità macOS (Fase A): capability flag dal backend + degradazione tollerante delle
feature Windows-only (loopback audio di sistema, temperatura CPU). I test mockano l'hardware:
il loopback non è disponibile su macOS/Linux (pyaudiowpatch è Windows-only)."""

from app import api as api_mod
from app.api import Api

from vokari.audio import capture


def test_system_audio_supported_windows_true(monkeypatch):
    monkeypatch.setattr(capture.sys, "platform", "win32")
    monkeypatch.setattr(capture, "_pyaudio", lambda: object())
    assert capture.system_audio_supported() is True


def test_system_audio_supported_windows_false_without_pyaudio(monkeypatch):
    monkeypatch.setattr(capture.sys, "platform", "win32")

    def _raise():
        raise RuntimeError("Cattura audio di sistema: richiede PyAudioWPatch (solo Windows).")

    monkeypatch.setattr(capture, "_pyaudio", _raise)
    assert capture.system_audio_supported() is False


def test_system_audio_supported_linux_true_with_monitor(monkeypatch):
    # Linux: la lane 'system' cattura da un device monitor (PipeWire/PulseAudio).
    monkeypatch.setattr(capture.sys, "platform", "linux")
    monkeypatch.setattr(capture, "_default_monitor_device", lambda: 3)
    assert capture.system_audio_supported() is True


def test_system_audio_supported_linux_false_without_monitor(monkeypatch):
    monkeypatch.setattr(capture.sys, "platform", "linux")
    monkeypatch.setattr(capture, "_default_monitor_device", lambda: None)
    assert capture.system_audio_supported() is False


def test_system_audio_supported_macos_false(monkeypatch):
    # macOS: nessun loopback nativo in v1 (servirebbe BlackHole/ScreenCaptureKit).
    monkeypatch.setattr(capture.sys, "platform", "darwin")
    assert capture.system_audio_supported() is False


def test_get_app_info_reports_platform_and_audio_cap(monkeypatch):
    monkeypatch.setattr(api_mod, "_platform_name", lambda: "macos")
    monkeypatch.setattr(capture, "system_audio_supported", lambda: False)
    info = Api().get_app_info()
    assert info["platform"] == "macos"
    assert info["systemAudioSupported"] is False
    # le chiavi storiche restano
    assert "version" in info and "githubStars" in info


def test_start_recording_coerces_to_mic_when_no_system_audio(monkeypatch):
    import types

    monkeypatch.setattr(capture, "system_audio_supported", lambda: False)
    monkeypatch.setattr(capture, "disk_preflight", lambda source: ("ok", float("inf")))
    fake_settings = types.SimpleNamespace(
        live_preview=False, live_model="m", whisper_model="m", transcription_language="it", app_language="it"
    )
    monkeypatch.setattr(api_mod.settings_mod, "load", lambda: fake_settings)

    started: dict = {}

    class _FakeRecorder:
        def __init__(self, source, out_path, **kw):
            started["source"] = source

        def start(self):
            started["started"] = True

    monkeypatch.setattr(capture, "Recorder", _FakeRecorder)

    api = Api()
    emitted: list = []
    monkeypatch.setattr(api, "_emit", lambda ev, payload: emitted.append((ev, payload)))

    res = api.start_recording("both")
    assert res["ok"] is True
    assert res["source"] == "mic"  # degradato dal loopback non disponibile
    assert started["source"] == "mic"  # il Recorder è stato creato con la sorgente coerciata
    assert any(ev == "warning" for ev, _ in emitted)  # l'utente è stato avvisato
