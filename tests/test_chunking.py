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


def test_split_wav_no_overlap_partitions_exactly(tmp_path):
    p = tmp_path / "a.wav"
    _make_wav(p, 5)
    chunks = list(chunking.split_wav(str(p), chunk_s=2, overlap_s=0))  # generatore -> materializza
    # 5s in chunk da 2s senza overlap -> 2 + 2 + 1
    assert len(chunks) == 3
    assert [round(c.offset_s, 3) for c in chunks] == [0.0, 2.0, 4.0]
    # finestre di accettazione contigue che coprono [0, +inf): prima da 0, ultima a +inf
    assert chunks[0].accept_lo == 0.0
    assert chunks[-1].accept_hi == float("inf")
    for i in range(len(chunks) - 1):
        assert chunks[i].accept_hi == chunks[i + 1].accept_lo
    # ogni chunk è un WAV valido riproducibile
    for c in chunks:
        with wave.open(io.BytesIO(c.data), "rb") as w:
            assert w.getframerate() == 16000
            assert w.getnchannels() == 1


def test_split_wav_overlap_makes_chunks_share_audio(tmp_path):
    p = tmp_path / "a.wav"
    _make_wav(p, 16)
    chunks = list(chunking.split_wav(str(p), chunk_s=10, overlap_s=4))
    # step = 10 - 4 = 6 -> offset 0 e 6 (il secondo arriva a fine = ultimo chunk)
    assert [round(c.offset_s, 3) for c in chunks] == [0.0, 6.0]
    # chunk0 [0,10] e chunk1 [6,16] si sovrappongono su [6,10];
    # il confine di accettazione cade alla METÀ dell'overlap: 6 + 4/2 = 8
    assert chunks[0].accept_lo == 0.0
    assert chunks[0].accept_hi == 8.0
    assert chunks[1].accept_lo == 8.0
    assert chunks[1].accept_hi == float("inf")


def test_split_wav_clamps_overlap_to_half_chunk(tmp_path):
    """overlap >= metà del chunk azzererebbe l'avanzamento (step<=0, loop infinito):
    viene clampato a chunk_s//2 -> gli offset restano crescenti e unici."""
    p = tmp_path / "a.wav"
    _make_wav(p, 6)
    chunks = list(chunking.split_wav(str(p), chunk_s=2, overlap_s=99))
    offs = [round(c.offset_s, 3) for c in chunks]
    assert offs[0] == 0.0
    assert offs == sorted(offs)
    assert len(set(offs)) == len(offs)  # nessun offset ripetuto (avanzamento garantito)


def test_apply_offset_shifts_timestamps():
    segs = [{"start": 0.0, "end": 1.0, "text": "a"}, {"start": 1.0, "end": 2.0, "text": "b"}]
    out = chunking.apply_offset(segs, 10.0)
    assert out[0]["start"] == 10.0 and out[0]["end"] == 11.0
    assert out[1]["start"] == 11.0 and out[1]["end"] == 12.0
    assert out[0]["text"] == "a"  # testo invariato
    # non muta l'input
    assert segs[0]["start"] == 0.0
