import io
import wave

from vokari.transcribe import chunking


def _make_wav(path, seconds, framerate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00\x00" * framerate * seconds)


def test_wav_duration(tmp_path):
    p = tmp_path / "a.wav"
    _make_wav(p, 3)
    assert abs(chunking.wav_duration(str(p)) - 3.0) < 0.01


def test_split_wav_produces_chunks_with_offsets(tmp_path):
    p = tmp_path / "a.wav"
    _make_wav(p, 5)
    chunks = list(chunking.split_wav(str(p), chunk_s=2))  # generatore -> materializza per il test
    # 5s in chunk da 2s -> 2 + 2 + 1
    assert len(chunks) == 3
    offsets = [round(off, 3) for _, off in chunks]
    assert offsets == [0.0, 2.0, 4.0]
    # ogni chunk è un WAV valido riproducibile
    for raw, _ in chunks:
        with wave.open(io.BytesIO(raw), "rb") as w:
            assert w.getframerate() == 16000
            assert w.getnchannels() == 1


def test_apply_offset_shifts_timestamps():
    segs = [{"start": 0.0, "end": 1.0, "text": "a"}, {"start": 1.0, "end": 2.0, "text": "b"}]
    out = chunking.apply_offset(segs, 10.0)
    assert out[0]["start"] == 10.0 and out[0]["end"] == 11.0
    assert out[1]["start"] == 11.0 and out[1]["end"] == 12.0
    assert out[0]["text"] == "a"  # testo invariato
    # non muta l'input
    assert segs[0]["start"] == 0.0
