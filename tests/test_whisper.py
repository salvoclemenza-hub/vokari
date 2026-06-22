import shutil
import wave

import pytest

from vokari.transcribe import chunking, whisper


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    # niente ffmpeg: la "normalizzazione" copia il sorgente (già WAV 16k mono)
    monkeypatch.setattr(
        whisper.convert, "to_wav_16k_mono", lambda src, dst: (shutil.copy(src, dst), chunking.wav_duration(dst))[1]
    )


def _make_wav(path, seconds, framerate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00\x00" * framerate * seconds)


def test_audio_hash_is_deterministic(tmp_path):
    p = tmp_path / "a.wav"
    _make_wav(p, 1)
    assert whisper.audio_hash(str(p)) == whisper.audio_hash(str(p))


def test_build_text_joins_segments():
    segs = [{"start": 0, "end": 1, "text": "Ciao"}, {"start": 1, "end": 2, "text": "mondo"}]
    assert whisper.build_text(segs) == "Ciao mondo"


def test_transcribe_uses_cache_on_second_run(tmp_path, monkeypatch):
    p = tmp_path / "a.wav"
    _make_wav(p, 2)
    calls = {"n": 0}

    def _fake_infer(audio, model_name, language):
        calls["n"] += 1
        return [{"start": 0.0, "end": 1.0, "text": "uno"}]

    monkeypatch.setattr(whisper, "_transcribe_audio", _fake_infer)

    r1 = whisper.transcribe(str(p), model="small", language="it")
    r2 = whisper.transcribe(str(p), model="small", language="it")
    assert r1["text"] == "uno" == r2["text"]
    assert calls["n"] == 1  # seconda esecuzione = cache hit, niente inferenza


def test_transcribe_chunks_long_audio_with_offsets(tmp_path, monkeypatch):
    p = tmp_path / "long.wav"
    _make_wav(p, 3)
    monkeypatch.setattr(chunking, "CHUNK_DURATION_S", 1)  # soglia bassa -> 3 chunk

    def _fake_infer(audio, model_name, language):
        return [{"start": 0.0, "end": 0.5, "text": "x"}]

    monkeypatch.setattr(whisper, "_transcribe_audio", _fake_infer)
    r = whisper.transcribe(str(p), model="small", language="auto")
    starts = [s["start"] for s in r["segments"]]
    assert starts == [0.0, 1.0, 2.0]  # offset applicati per chunk


def test_skips_reconversion_when_already_16k_mono(tmp_path, monkeypatch):
    """Un WAV già 16k mono (tipico delle registrazioni) NON viene ri-convertito da ffmpeg (R4)."""
    p = tmp_path / "rec.wav"
    _make_wav(p, 1)  # 16k mono
    called = {"n": 0}

    def fake_convert(src, dst):
        called["n"] += 1
        shutil.copy(src, dst)

    monkeypatch.setattr(whisper.convert, "to_wav_16k_mono", fake_convert)
    monkeypatch.setattr(
        whisper, "_transcribe_audio", lambda audio, model_name, language: [{"start": 0.0, "end": 1.0, "text": "x"}]
    )
    whisper.transcribe(str(p), model="small", language="it")
    assert called["n"] == 0  # nessuna passata ffmpeg


def test_converts_when_not_16k_mono(tmp_path, monkeypatch):
    """Un sorgente non-16k (es. import) viene convertito (R4 non lo salta)."""
    p = tmp_path / "src.wav"
    _make_wav(p, 1, framerate=44100)  # NON 16k
    called = {"n": 0}

    def fake_convert(src, dst):
        called["n"] += 1
        _make_wav(dst, 1)  # produce un 16k mono valido

    monkeypatch.setattr(whisper.convert, "to_wav_16k_mono", fake_convert)
    monkeypatch.setattr(
        whisper, "_transcribe_audio", lambda audio, model_name, language: [{"start": 0.0, "end": 1.0, "text": "x"}]
    )
    whisper.transcribe(str(p), model="small", language="it")
    assert called["n"] == 1  # conversione eseguita


def test_load_model_is_cached(monkeypatch):
    """Il modello Whisper si carica una sola volta per nome (no reload per-chunk)."""
    import faster_whisper

    calls = {"n": 0}

    class _FakeModel:
        def __init__(self, *a, **k):
            calls["n"] += 1

    monkeypatch.setattr(faster_whisper, "WhisperModel", _FakeModel)
    whisper._load_model.cache_clear()
    try:
        m1 = whisper._load_model("small")
        m2 = whisper._load_model("small")
        assert m1 is m2
        assert calls["n"] == 1  # costruito una volta sola
    finally:
        whisper._load_model.cache_clear()


@pytest.mark.slow
def test_transcribe_real_clip(tmp_path):
    pytest.skip("richiede modello Whisper scaricato + ffmpeg: verifica manuale")
