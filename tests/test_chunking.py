import io
import wave
from itertools import pairwise

import numpy as np

from vokari.transcribe import chunking
from vokari.transcribe import chunking as C


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


# --- Il taglio cerca il silenzio (2026-09-25) ---------------------------------
# I chunk si tagliavano a 600s esatti, cioè quasi sempre in mezzo a una parola: Whisper
# riparte da un frammento e in quel punto tende ad allucinare. Ora il confine si sposta
# ALL'INDIETRO fino al punto più silenzioso della zona di ricerca — ma solo se c'è un
# guadagno vero, altrimenti resta dov'era (audio uniforme: niente da guadagnare).


def _voiced(n, amp=8000, seed=0):
    rng = np.random.default_rng(seed)
    return (rng.normal(0, amp / 3, n)).astype(np.int16)


def test_quietest_offset_finds_the_gap():
    samples = np.concatenate([_voiced(1000), np.zeros(200, dtype=np.int16), _voiced(1000)])
    found = C.quietest_offset(samples, center=1400, search=600, win=50)
    assert 1000 <= found <= 1200, f"atteso dentro il silenzio, trovato {found}"


def test_quietest_offset_keeps_the_boundary_when_there_is_nothing_to_gain():
    """Audio uniforme (o tutto silenzio): spostare il taglio non migliora niente."""
    samples = _voiced(3000)
    assert C.quietest_offset(samples, center=2000, search=600, win=50) == 2000


def test_split_wav_moves_the_cut_into_the_silence(tmp_path):
    p = tmp_path / "gap.wav"
    fr = 16000
    body = np.concatenate(
        [
            _voiced(fr * 1),  # 0.0-1.0s parlato
            np.zeros(int(fr * 0.2), dtype=np.int16),  # 1.0-1.2s silenzio
            _voiced(fr * 3),  # fino a 4.2s
        ]
    )
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fr)
        w.writeframes(body.tobytes())

    chunks = list(C.split_wav(str(p), chunk_s=2, overlap_s=0))
    # senza ricerca il secondo chunk partirebbe a 2.0s, in mezzo al parlato: ora va nel silenzio
    assert 1.0 <= chunks[1].offset_s <= 1.25, [c.offset_s for c in chunks]


def test_split_wav_still_covers_all_the_audio_after_moving_the_cut(tmp_path):
    """Spostare il taglio non deve far sparire audio: i chunk coprono tutto, in ordine."""
    p = tmp_path / "gap2.wav"
    fr = 16000
    body = np.concatenate([_voiced(fr), np.zeros(int(fr * 0.2), dtype=np.int16), _voiced(fr * 3)])
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fr)
        w.writeframes(body.tobytes())

    chunks = list(C.split_wav(str(p), chunk_s=2, overlap_s=0))
    assert chunks[0].offset_s == 0.0
    for a, b in pairwise(chunks):
        with wave.open(io.BytesIO(a.data), "rb") as w:
            fine_a = a.offset_s + w.getnframes() / w.getframerate()
        assert b.offset_s <= fine_a, "un buco fra due chunk = audio perso"
    assert chunks[-1].accept_hi == float("inf")
