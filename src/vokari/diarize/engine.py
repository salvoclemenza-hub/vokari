"""Diarization locale su CPU con sherpa-onnx (opzionale).

Perche' sherpa-onnx e non pyannote: e' un wheel da ~28 MB con il suo onnxruntime, senza
torch e senza token HuggingFace, e i modelli pesano ~35 MB scaricati a richiesta — contro
&gt;120 MB di solo torch e un account esterno per i modelli gated. Misurato su CPU: RTF
0,06-0,13, cioe' 10-15x piu' veloce del tempo reale, marginale accanto alla trascrizione.

Il pacchetto e' **opzionale** e sta dietro un import lazy (come `sounddevice` per la
cattura): chi non usa la funzione non se ne accorge, e l'app parte anche senza.

⚠ Su un audio "both" (microfono + sistema) mixato in mono la diarization degrada: le voci
si sovrappongono nello stesso canale. E' scritto nella UI, non nascosto.
"""

import ctypes
import os
import sys
import tarfile
import urllib.request
import wave
from pathlib import Path
from typing import NamedTuple

from vokari.diarize.speakers import Turn
from vokari.paths import ensure_dirs

# Release di k2-fsa/sherpa-onnx. ⚠ "recongition" e' un refuso a monte: corretto qui = 404.
_SEG_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/"
    "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
)
_EMB_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
    "3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx"
)
_SEG_REL = "sherpa-onnx-pyannote-segmentation-3-0/model.onnx"
_EMB_REL = "3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx"

# Soglia di clustering quando il numero di partecipanti non e' noto. Con il numero noto la
# qualita' e' nettamente migliore (misurato: 2 speaker corretti contro 4 cluster inventati).
_CLUSTER_THRESHOLD = 0.5
_SAMPLE_RATE = 16000


class Models(NamedTuple):
    segmentation: Path
    embedding: Path


_IS_WINDOWS = sys.platform.startswith("win")


def _load_dll(path) -> None:
    ctypes.WinDLL(str(path))


def _prefer_bundled_onnxruntime() -> None:
    """Su Windows fa vincere l'onnxruntime del venv su quello di sistema.

    `sherpa_onnx` si collega a `onnxruntime.dll` per nome, e su Windows quel nome esiste
    anche in `System32` (lo installa WinML, versione vecchia): il caricatore trova quello e
    sherpa muore con «The requested API version [28] is not available». Registrare la
    cartella `onnxruntime/capi` del venv e pre-caricare da li' la DLL risolve, perche' una
    libreria gia' in memoria con quel nome viene riusata.

    Tollerante: qualunque intoppo qui non deve impedire l'import — al massimo si ricade nel
    comportamento di prima, con l'errore esplicito di sherpa."""
    if not _IS_WINDOWS:
        return
    try:
        import onnxruntime

        capi = Path(onnxruntime.__file__).parent / "capi"
        if capi.is_dir():
            os.add_dll_directory(str(capi))
            _load_dll(capi / "onnxruntime.dll")
    except Exception:  # noqa: S110 — diagnostica: l'import sotto dira' comunque cosa non va
        pass


def _sherpa():
    """Import lazy: senza il pacchetto l'app funziona lo stesso, solo senza speaker."""
    _prefer_bundled_onnxruntime()
    import sherpa_onnx

    return sherpa_onnx


def is_available() -> bool:
    """True se sherpa-onnx e' installato (il download dei modelli e' un'altra cosa)."""
    try:
        _sherpa()
    except Exception:
        return False
    return True


def model_dir() -> Path:
    return ensure_dirs().models / "diarization"


def models() -> Models:
    d = model_dir()
    return Models(segmentation=d / _SEG_REL, embedding=d / _EMB_REL)


def models_ready() -> bool:
    return all(p.exists() for p in models())


def download_models(on_progress=None) -> Models:
    """Scarica i due modelli (~35 MB) in `userData/models/diarization`. Idempotente.

    `on_progress(fatto, totale)` riceve il numero di file completati."""
    d = model_dir()
    d.mkdir(parents=True, exist_ok=True)
    m = models()
    if not m.segmentation.exists():
        archivio = d / "segmentation.tar.bz2"
        urllib.request.urlretrieve(_SEG_URL, archivio)  # noqa: S310 — URL costante, https
        with tarfile.open(archivio, "r:bz2") as tar:
            tar.extractall(d, filter="data")  # filter="data": niente path assoluti o symlink
        archivio.unlink(missing_ok=True)
    if on_progress:
        on_progress(1, 2)
    if not m.embedding.exists():
        urllib.request.urlretrieve(_EMB_URL, m.embedding)  # noqa: S310 — URL costante, https
    if on_progress:
        on_progress(2, 2)
    return m


def _read_wav_16k_mono(path: str):
    """Campioni float32 in [-1, 1]. sherpa-onnx non ricampiona: il WAV e' gia' normalizzato
    a 16k mono dalla pipeline (`convert.to_wav_16k_mono`)."""
    import numpy as np

    with wave.open(path, "rb") as w:
        if w.getframerate() != _SAMPLE_RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise RuntimeError("la diarization vuole un WAV 16 kHz mono PCM16")
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype("float32") / 32768.0


def diarize_wav(wav_path: str, *, num_speakers: int = 0, on_progress=None, should_cancel=None) -> list[Turn]:
    """Turni `(start, end, speaker)` del file. Solleva se i modelli non ci sono.

    `num_speakers=0` = stima automatica (piu' fragile: tende a spezzare una persona in due).
    `should_cancel` e' onorato durante l'elaborazione, non solo prima: su una riunione lunga
    e' la differenza fra Annulla che risponde e Annulla che sembra ignorato."""
    if should_cancel and should_cancel():
        return []
    if not models_ready():
        raise RuntimeError("modelli di diarization non scaricati")
    sherpa = _sherpa()
    m = models()
    seg = sherpa.OfflineSpeakerSegmentationModelConfig(
        pyannote=sherpa.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(m.segmentation)),
        num_threads=1,
    )
    emb = sherpa.SpeakerEmbeddingExtractorConfig(model=str(m.embedding), num_threads=1)
    clustering = (
        sherpa.FastClusteringConfig(num_clusters=num_speakers)
        if num_speakers and num_speakers > 1
        else sherpa.FastClusteringConfig(threshold=_CLUSTER_THRESHOLD)
    )
    config = sherpa.OfflineSpeakerDiarizationConfig(
        segmentation=seg,
        embedding=emb,
        clustering=clustering,
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    diar = sherpa.OfflineSpeakerDiarization(config)

    def _cb(fatti: int, totali: int) -> int:
        if on_progress:
            on_progress(fatti, totali)
        return 1 if (should_cancel and should_cancel()) else 0  # non-zero = abortisci

    result = diar.process(_read_wav_16k_mono(wav_path), callback=_cb)
    if should_cancel and should_cancel():
        return []
    return [Turn(start=float(s.start), end=float(s.end), speaker=int(s.speaker)) for s in result.sort_by_start_time()]
