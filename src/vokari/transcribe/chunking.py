"""Suddivisione WAV in chunk e shift timestamp. Port puro da transcriber.py legacy.

L17 (overlap): i chunk si sovrappongono di `OVERLAP_DURATION_S` secondi così che una frase
a cavallo del confine sia trascritta INTERA da almeno un chunk (senza overlap veniva tagliata
a metà in entrambi). Per non avere testo duplicato nella zona di sovrapposizione, ogni chunk
porta una FINESTRA DI ACCETTAZIONE `[accept_lo, accept_hi)` in tempo assoluto: il confine tra
due chunk cade alla METÀ dell'overlap, così ogni istante dell'audio è "di proprietà" di un solo
chunk. Il consumatore tiene un segmento solo se il suo start (dopo `apply_offset`) cade nella
finestra del chunk → niente parole tagliate, niente duplicati."""

import io
import wave
from collections.abc import Iterator
from typing import NamedTuple

# Durata massima di un singolo chunk inviato all'inferenza (10 minuti).
CHUNK_DURATION_S = 600

# Sovrapposizione tra chunk consecutivi (secondi). Deve superare la durata di una frase
# tipica al confine; 5s è ampio e aggiunge <1% di audio ri-trascritto per chunk da 10min.
OVERLAP_DURATION_S = 5

# Quanto si può arretrare il taglio per farlo cadere in un silenzio (secondi). Il taglio a
# tempo fisso cade quasi sempre in mezzo a una parola: Whisper riparte da un frammento e
# proprio lì tende ad allucinare. Si cerca ALL'INDIETRO (mai in avanti: il chunk non deve
# crescere) e ci si sposta solo se il guadagno è reale.
BOUNDARY_SEARCH_S = 15
# Finestra su cui si misura l'energia, in millisecondi.
_RMS_WINDOW_MS = 50
# Ci si sposta solo se il punto candidato è almeno la metà meno sonoro di quello nominale:
# su audio uniforme (o tutto silenzio) non c'è niente da guadagnare e il taglio resta dov'era.
_QUIET_GAIN = 0.5


class Chunk(NamedTuple):
    """Un chunk WAV con il suo offset e la finestra di accettazione (tempo assoluto, secondi).

    `offset_s` va passato ad `apply_offset`; `accept_lo`/`accept_hi` selezionano i segmenti
    che appartengono a questo chunk (vedi modulo). `accept_hi` è `inf` per l'ultimo chunk."""

    data: bytes
    offset_s: float
    accept_lo: float
    accept_hi: float


def quietest_offset(samples, center: int, search: int, win: int) -> int:
    """Indice del punto più silenzioso in `[center-search, center]`, o `center` se spostarsi
    non porta un guadagno vero. Puro: lavora su un array di campioni interi.

    `samples` è un array numpy di PCM16 mono; `center`, `search` e `win` sono in campioni."""
    import numpy as np

    lo = max(0, center - search)
    if center <= lo or win <= 0 or len(samples) < center:
        return center
    a = np.asarray(samples[lo:center], dtype=np.float64)
    n_win = len(a) // win
    if n_win < 2:
        return center
    energia = np.sqrt((a[: n_win * win].reshape(n_win, win) ** 2).mean(axis=1))
    i_min = int(energia.argmin())
    coda = np.asarray(samples[max(0, center - win) : center], dtype=np.float64)
    rms_nominale = float(np.sqrt((coda**2).mean())) if len(coda) else 0.0
    if energia[i_min] >= rms_nominale * _QUIET_GAIN:
        return center  # niente di meglio del punto in cui saremmo tagliati comunque
    return lo + i_min * win + win // 2


def _pcm16_mono(raw: bytes, n_channels: int, sampwidth: int):
    """Array numpy dei campioni, o None se il formato non è PCM16 mono (nessun aggiustamento:
    meglio il taglio a tempo fisso che un'interpretazione sbagliata dei byte)."""
    if n_channels != 1 or sampwidth != 2:
        return None
    try:
        import numpy as np

        return np.frombuffer(raw, dtype=np.int16)
    except Exception:
        return None


def wav_duration(wav_path: str) -> float:
    """Durata di un file WAV in secondi."""
    with wave.open(wav_path, "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def split_wav(wav_path: str, chunk_s: int = CHUNK_DURATION_S, overlap_s: int | None = None) -> Iterator[Chunk]:
    """Genera i chunk di un WAV uno per volta come `Chunk(data, offset_s, accept_lo, accept_hi)`.

    Generatore (non lista): su file lunghi tiene in RAM un solo chunk alla volta invece di
    materializzarli tutti (R3). I chunk si sovrappongono di `overlap_s` secondi (default
    `OVERLAP_DURATION_S`, letto a runtime così resta monkeypatchabile nei test). L'overlap è
    clampato a metà del chunk per garantire `step > 0` (niente loop infinito su chunk piccoli)."""
    if overlap_s is None:
        overlap_s = OVERLAP_DURATION_S
    overlap_s = max(0, min(overlap_s, chunk_s // 2))
    step_s = chunk_s - overlap_s  # avanzamento tra un offset e il successivo; >= chunk_s/2 > 0

    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        total_frames = wf.getnframes()
        chunk_frames = chunk_s * framerate
        step_frames = step_s * framerate

        offset = 0
        index = 0
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

            offset_sec = offset / framerate
            is_last = offset + chunk_frames >= total_frames

            # Dove comincia il prossimo chunk: il passo nominale, arretrato fino al punto più
            # silenzioso se ce n'è uno (così Whisper non riparte da mezza parola). La ricerca
            # guarda solo INDIETRO: il chunk corrente copre già quell'audio, quindi spostare
            # il taglio non può aprire buchi.
            passo = step_frames
            if not is_last:
                samples = _pcm16_mono(raw, n_channels, sampwidth)
                if samples is not None:
                    passo = quietest_offset(
                        samples,
                        center=step_frames,
                        search=min(BOUNDARY_SEARCH_S * framerate, step_frames // 2),
                        win=max(1, _RMS_WINDOW_MS * framerate // 1000),
                    )
            next_sec = (offset + passo) / framerate

            # Confine alla metà dell'overlap fra questo chunk e il prossimo.
            accept_lo = 0.0 if index == 0 else offset_sec + overlap_s / 2
            accept_hi = float("inf") if is_last else next_sec + overlap_s / 2
            yield Chunk(buf.getvalue(), offset_sec, accept_lo, accept_hi)

            if is_last:
                break
            offset += passo
            index += 1


def apply_offset(segments: list[dict], offset_s: float) -> list[dict]:
    """Ritorna nuovi segmenti con start/end shiftati di offset_s (non muta l'input)."""
    return [
        {**seg, "start": round(seg["start"] + offset_s, 3), "end": round(seg["end"] + offset_s, 3)} for seg in segments
    ]
