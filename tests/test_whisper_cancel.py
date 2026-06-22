import json

from vokari.transcribe import whisper as W


class _Seg:
    def __init__(self, i):
        self.start = float(i)
        self.end = float(i) + 1.0
        self.text = f"seg{i}"


class _FakeModel:
    def transcribe(self, audio, language=None, beam_size=5, **_):
        return ((_Seg(i) for i in range(100)), object())


def test_iter_transcribe_honors_should_cancel(monkeypatch):
    monkeypatch.setattr(W, "_load_model", lambda name: _FakeModel())
    seen = []

    def should_cancel():
        return len(seen) >= 3

    for seg in W._iter_transcribe("x.wav", "base", "auto", should_cancel=should_cancel):
        seen.append(seg)
    assert len(seen) == 3, f"atteso stop a 3 segmenti, visti {len(seen)}"


def test_transcribe_stream_cache_hit_returns_from_cache(tmp_path, monkeypatch):
    """Cache hit: il result deve avere from_cache=True e on_segment riceve from_cache=True."""
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"\x00" * 100)
    key = f"{W.audio_hash(str(audio))}-large-v3-turbo-it"
    cached = {
        "source": str(audio),
        "model": "large-v3-turbo",
        "language": "it",
        "duration_s": 1.0,
        "segments": [],
        "text": "ciao mondo",
    }
    W._cache_path(key).write_text(json.dumps(cached), encoding="utf-8")
    result = W.transcribe_stream(str(audio), model="large-v3-turbo", language="it")
    assert result.get("from_cache") is True
    assert result["text"] == "ciao mondo"


def test_transcribe_stream_cache_hit_on_segment_receives_from_cache(tmp_path, monkeypatch):
    """Cache hit: on_segment viene chiamato con kwarg from_cache=True."""
    audio = tmp_path / "test2.wav"
    audio.write_bytes(b"\x00" * 100)
    key = f"{W.audio_hash(str(audio))}-large-v3-turbo-it"
    cached = {
        "source": str(audio),
        "model": "large-v3-turbo",
        "language": "it",
        "duration_s": 1.0,
        "segments": [],
        "text": "ciao mondo",
    }
    W._cache_path(key).write_text(json.dumps(cached), encoding="utf-8")
    calls = []

    def on_seg(pct, text_so_far, seg_text, from_cache=False, **kwargs):
        calls.append({"pct": pct, "from_cache": from_cache})

    W.transcribe_stream(str(audio), model="large-v3-turbo", language="it", on_segment=on_seg)
    assert len(calls) == 1
    assert calls[0]["from_cache"] is True
