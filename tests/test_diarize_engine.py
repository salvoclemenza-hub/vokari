"""Il motore della diarization: modelli, disponibilità, chiamata a sherpa-onnx.

Nessun modello reale e nessuna rete nei test (ADR-061): sherpa-onnx è dietro un import
lazy, esattamente come `sounddevice` per la cattura, quindi si può sostituire con un finto.
"""

import wave

import pytest

from vokari.diarize import engine


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))


def _wav(path, seconds=1):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000 * seconds)
    return str(path)


def test_not_available_without_the_package(monkeypatch):
    """Senza sherpa-onnx installato l'app non deve rompersi: la funzione è opzionale."""
    monkeypatch.setattr(engine, "_sherpa", lambda: (_ for _ in ()).throw(ImportError("no sherpa")))
    assert engine.is_available() is False


def test_models_are_not_ready_on_a_fresh_install():
    assert engine.models_ready() is False


class _FakeSegment:
    def __init__(self, start, end, speaker):
        self.start, self.end, self.speaker = start, end, speaker


class _FakeResult:
    def sort_by_start_time(self):
        return [_FakeSegment(0.0, 2.0, 0), _FakeSegment(2.0, 5.0, 1)]


class _FakeDiar:
    last_config = None

    def __init__(self, config):
        _FakeDiar.last_config = config

    def process(self, samples, callback=None):
        assert len(samples), "i campioni devono arrivare al motore"
        if callback:
            callback(1, 2)
        return _FakeResult()


class _FakeSherpa:
    """Solo ciò che serve: le config sono namespace che registrano i kwargs."""

    def __getattr__(self, name):
        if name == "OfflineSpeakerDiarization":
            return _FakeDiar
        return lambda **kw: {"_cls": name, **kw}


def test_diarize_returns_turns_in_order(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "_sherpa", _FakeSherpa)
    monkeypatch.setattr(engine, "models_ready", lambda: True)
    turni = engine.diarize_wav(_wav(tmp_path / "a.wav", 5), num_speakers=2)
    assert [(t.start, t.end, t.speaker) for t in turni] == [(0.0, 2.0, 0), (2.0, 5.0, 1)]


def test_known_speaker_count_is_passed_to_the_clustering(monkeypatch, tmp_path):
    """Con il numero di partecipanti noto la qualità sale molto: non va perso per strada."""
    monkeypatch.setattr(engine, "_sherpa", _FakeSherpa)
    monkeypatch.setattr(engine, "models_ready", lambda: True)
    engine.diarize_wav(_wav(tmp_path / "b.wav"), num_speakers=3)
    assert _FakeDiar.last_config["clustering"]["num_clusters"] == 3


def test_unknown_speaker_count_uses_a_threshold(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "_sherpa", _FakeSherpa)
    monkeypatch.setattr(engine, "models_ready", lambda: True)
    engine.diarize_wav(_wav(tmp_path / "c.wav"), num_speakers=0)
    clustering = _FakeDiar.last_config["clustering"]
    assert "num_clusters" not in clustering and clustering["threshold"] > 0


def test_missing_models_raise_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "_sherpa", _FakeSherpa)
    with pytest.raises(RuntimeError):
        engine.diarize_wav(_wav(tmp_path / "d.wav"))


def test_cancel_stops_the_work(monkeypatch, tmp_path):
    """La diarization gira dopo una trascrizione già lunga: Annulla deve poterla fermare."""
    monkeypatch.setattr(engine, "_sherpa", _FakeSherpa)
    monkeypatch.setattr(engine, "models_ready", lambda: True)
    turni = engine.diarize_wav(_wav(tmp_path / "e.wav"), should_cancel=lambda: True)
    assert turni == []


def test_windows_loads_the_bundled_onnxruntime_first(monkeypatch):
    """Su Windows `C:\Windows\System32\onnxruntime.dll` (vecchia, di sistema) vince sul
    runtime del pacchetto e sherpa-onnx muore con «API version 28 not available». Prima di
    importarlo si registra la cartella del runtime giusto: senza, la diarization non parte
    su nessun PC Windows che abbia WinML — cioè quasi tutti. Trovato provando davvero,
    non dai test con il motore finto."""
    registrate: list[str] = []
    monkeypatch.setattr(engine.os, "add_dll_directory", lambda p: registrate.append(p) or None, raising=False)
    monkeypatch.setattr(engine, "_IS_WINDOWS", True)
    caricate: list[str] = []
    monkeypatch.setattr(engine, "_load_dll", lambda p: caricate.append(str(p)))
    engine._prefer_bundled_onnxruntime()
    assert registrate and any("capi" in p for p in registrate)
    assert caricate and caricate[0].endswith("onnxruntime.dll")
