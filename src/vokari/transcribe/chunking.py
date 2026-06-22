"""Suddivisione WAV in chunk e shift timestamp. Port puro da transcriber.py legacy."""

import io
import wave
from collections.abc import Iterator

# Durata massima di un singolo chunk inviato all'inferenza (10 minuti).
CHUNK_DURATION_S = 600


def wav_duration(wav_path: str) -> float:
    """Durata di un file WAV in secondi."""
    with wave.open(wav_path, "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def split_wav(wav_path: str, chunk_s: int = CHUNK_DURATION_S) -> Iterator[tuple[bytes, float]]:
    """Genera i chunk di un WAV uno per volta come (wav_bytes, offset_s).

    Generatore (non lista): su file lunghi tiene in RAM un solo chunk alla volta invece
    di materializzarli tutti (R3). I consumatori già iterano (`for raw, off in split_wav`)."""
    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        total_frames = wf.getnframes()
        chunk_frames = chunk_s * framerate

        offset = 0
        while offset < total_frames:
            wf.setpos(offset)
            n = min(chunk_frames, total_frames - offset)
            raw = wf.readframes(n)

            buf = io.BytesIO()
            with wave.open(buf, "wb") as out:
                out.setnchannels(n_channels)
                out.setsampwidth(sampwidth)
                out.setframerate(framerate)
                out.writeframes(raw)
            yield buf.getvalue(), offset / framerate
            offset += n


def apply_offset(segments: list[dict], offset_s: float) -> list[dict]:
    """Ritorna nuovi segmenti con start/end shiftati di offset_s (non muta l'input)."""
    return [
        {**seg, "start": round(seg["start"] + offset_s, 3), "end": round(seg["end"] + offset_s, 3)} for seg in segments
    ]
