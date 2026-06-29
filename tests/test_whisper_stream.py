import wave
from pathlib import Path

import pytest

from vokari.transcribe import whisper as W


def _silent_wav(path: Path, seconds: float = 1.0, rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * int(rate * seconds))


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    W._load_model.cache_clear()
    return tmp_path


def test_transcribe_stream_emits_progress_and_caches(home, tmp_path, monkeypatch):
    src = tmp_path / "a.wav"
    _silent_wav(src, seconds=1.0)
    fake_segments = [
        {"start": 0.0, "end": 0.5, "text": "ciao"},
        {"start": 0.5, "end": 1.0, "text": "mondo"},
    ]
    monkeypatch.setattr(
        W, "_iter_transcribe", lambda audio, m, lang, should_cancel=None, initial_prompt="": iter(fake_segments)
    )

    events: list[tuple[float, str, str]] = []
    result = W.transcribe_stream(
        str(src),
        model="small",
        language="it",
        on_segment=lambda pct, text_so_far, seg: events.append((pct, text_so_far, seg)),
    )

    assert result["text"] == "ciao mondo"
    assert [e[2] for e in events] == ["ciao", "mondo"]
    assert events[0][0] == pytest.approx(0.5, abs=0.01)
    assert events[1][0] == pytest.approx(1.0, abs=0.01)
    assert events[1][1] == "ciao mondo"


def test_transcribe_stream_cache_hit_emits_once_full(home, tmp_path, monkeypatch):
    src = tmp_path / "b.wav"
    _silent_wav(src, seconds=1.0)
    fake = [{"start": 0.0, "end": 1.0, "text": "uno due"}]
    monkeypatch.setattr(W, "_iter_transcribe", lambda audio, m, lang, should_cancel=None, initial_prompt="": iter(fake))
    W.transcribe_stream(str(src), model="small", language="it")  # popola cache

    def boom(*a, **k):
        raise AssertionError("non deve ri-trascrivere su cache hit")

    monkeypatch.setattr(W, "_iter_transcribe", boom)
    seen: list[tuple[float, str, str]] = []
    out = W.transcribe_stream(
        str(src), model="small", language="it", on_segment=lambda p, t, s, **k: seen.append((p, t, s))
    )
    assert out["text"] == "uno due"
    assert seen == [(1.0, "uno due", "uno due")]


def test_transcribe_stream_cancel_does_not_cache(home, tmp_path, monkeypatch):
    """Contratto chiave: una trascrizione annullata ritorna cancelled=True e NON scrive
    cache (eviterebbe di cachare un parziale come se fosse completo)."""
    src = tmp_path / "c.wav"
    _silent_wav(src, seconds=1.0)
    fake = [{"start": 0.0, "end": 0.5, "text": "a"}, {"start": 0.5, "end": 1.0, "text": "b"}]
    monkeypatch.setattr(W, "_iter_transcribe", lambda audio, m, lang, should_cancel=None, initial_prompt="": iter(fake))

    out = W.transcribe_stream(str(src), model="small", language="it", should_cancel=lambda: True)

    assert out.get("cancelled") is True
    key = f"{W.audio_hash(str(src))}-small-it"
    assert not W._cache_path(key).exists(), "su cancel NON deve scrivere la cache"
