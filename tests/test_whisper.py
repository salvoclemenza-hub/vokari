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

    def _fake_infer(audio, model_name, language, initial_prompt=""):
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

    def _fake_infer(audio, model_name, language, initial_prompt=""):
        return [{"start": 0.0, "end": 0.5, "text": "x"}]

    monkeypatch.setattr(whisper, "_transcribe_audio", _fake_infer)
    r = whisper.transcribe(str(p), model="small", language="auto")
    starts = [s["start"] for s in r["segments"]]
    assert starts == [0.0, 1.0, 2.0]  # offset applicati per chunk


def test_transcribe_dedupes_overlapping_chunk_segments(tmp_path, monkeypatch):
    """L17: con chunk sovrapposti un segmento nella zona di overlap appartiene a UN solo
    chunk (confine al midpoint dell'overlap) -> niente duplicati, niente frasi perse al confine."""
    p = tmp_path / "long.wav"
    _make_wav(p, 16)
    monkeypatch.setattr(chunking, "CHUNK_DURATION_S", 10)
    monkeypatch.setattr(chunking, "OVERLAP_DURATION_S", 4)

    # ogni chunk (10s) restituisce gli stessi segmenti RELATIVI: 0.0 e 7.5
    def _fake_infer(audio, model_name, language, initial_prompt=""):
        return [{"start": 0.0, "end": 0.5, "text": "a"}, {"start": 7.5, "end": 8.0, "text": "b"}]

    monkeypatch.setattr(whisper, "_transcribe_audio", _fake_infer)
    monkeypatch.setattr(whisper, "detect_language", lambda wav_path, model_name: ("it", 0.9))
    r = whisper.transcribe(str(p), model="small", language="auto")
    starts = [s["start"] for s in r["segments"]]
    # chunk0 offset 0 -> abs 0.0 e 7.5 (finestra [0,8): entrambi tenuti)
    # chunk1 offset 6 -> abs 6.0 (SCARTATO: <8, già coperto da chunk0) e 13.5 (tenuto)
    assert starts == [0.0, 7.5, 13.5]


def test_transcribe_stream_dedupes_overlapping_chunk_segments(tmp_path, monkeypatch):
    """Stesso dedup nel path streaming: i segmenti scartati non vengono né accumulati né emessi."""
    p = tmp_path / "long.wav"
    _make_wav(p, 16)
    monkeypatch.setattr(chunking, "CHUNK_DURATION_S", 10)
    monkeypatch.setattr(chunking, "OVERLAP_DURATION_S", 4)

    def _fake_iter(audio, model_name, language, should_cancel=None, initial_prompt=""):
        yield {"start": 0.0, "end": 0.5, "text": "a"}
        yield {"start": 7.5, "end": 8.0, "text": "b"}

    monkeypatch.setattr(whisper, "_iter_transcribe", _fake_iter)
    monkeypatch.setattr(whisper, "detect_language", lambda wav_path, model_name: ("it", 0.9))
    emitted: list[str] = []
    r = whisper.transcribe_stream(
        str(p),
        model="small",
        language="auto",
        on_segment=lambda pct, text, seg_text, **kw: emitted.append(seg_text),
    )
    assert [s["start"] for s in r["segments"]] == [0.0, 7.5, 13.5]
    assert emitted == ["a", "b", "b"]  # il duplicato @6.0 non viene emesso


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
        whisper,
        "_transcribe_audio",
        lambda audio, model_name, language, initial_prompt="": [{"start": 0.0, "end": 1.0, "text": "x"}],
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
        whisper,
        "_transcribe_audio",
        lambda audio, model_name, language, initial_prompt="": [{"start": 0.0, "end": 1.0, "text": "x"}],
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


def test_transcribe_captures_detected_language(tmp_path, monkeypatch):
    """L09: transcribe espone la lingua RILEVATA (detect_language) nel result, distinta dalla
    lingua richiesta. Tollerante: _transcribe_audio è mockato, detect_language pure."""
    from vokari.transcribe import whisper as W

    wav = tmp_path / "a.wav"
    _make_wav(wav, 1)  # helper ESISTENTE in test_whisper.py: _make_wav(path, seconds, framerate=16000)
    monkeypatch.setattr(
        W,
        "_transcribe_audio",
        lambda audio, model, language, initial_prompt="": [{"start": 0.0, "end": 1.0, "text": "ciao"}],
    )
    monkeypatch.setattr(W, "detect_language", lambda wav_path, model_name: ("en", 0.97))

    res = W.transcribe(str(wav), model="small", language="it")
    assert res["language"] == "it"  # richiesta (invariata)
    assert res["detected_language"] == "en"  # rilevata
    assert res["language_probability"] == 0.97


def test_transcribe_tolerates_detect_language_failure(tmp_path, monkeypatch):
    """Se detect_language solleva (modello assente), il result ha detected_language='' e
    la trascrizione procede normalmente (mai fatale)."""
    from vokari.transcribe import whisper as W

    wav = tmp_path / "b.wav"
    _make_wav(wav, 1)
    monkeypatch.setattr(
        W,
        "_transcribe_audio",
        lambda audio, model, language, initial_prompt="": [{"start": 0.0, "end": 1.0, "text": "x"}],
    )

    def _boom(wav_path, model_name):
        raise RuntimeError("modello non scaricato")

    monkeypatch.setattr(W, "detect_language", _boom)
    res = W.transcribe(str(wav), model="small", language="it")
    assert res["detected_language"] == ""
    assert res["language_probability"] == 0.0
    assert res["text"] == "x"


@pytest.mark.slow
def test_transcribe_real_clip(tmp_path):
    pytest.skip("richiede modello Whisper scaricato + ffmpeg: verifica manuale")
