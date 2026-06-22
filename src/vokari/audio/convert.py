"""Conversione audio -> WAV 16kHz mono (richiesto da Whisper). Richiede ffmpeg."""

import shutil
import subprocess

from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError


class AudioConversionError(RuntimeError):
    """Errore di conversione audio: file corrotto, formato non supportato o ffmpeg fallito."""

    def __init__(self, src_path: str, cause: Exception):
        super().__init__(
            f"Impossibile convertire '{src_path}': {cause}. "
            "Verifica che il file audio non sia corrotto e che ffmpeg sia aggiornato."
        )
        self.__cause__ = cause
        self.path = src_path


def check_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg non trovato nel PATH. Installa ffmpeg (https://ffmpeg.org/download.html) e aggiungilo al PATH."
        )


def probe_duration_s(path: str) -> float | None:
    """Durata in secondi via ffprobe (veloce, NON decodifica l'intero file come pydub). None se
    non determinabile (ffprobe assente, file mancante/illeggibile) — best-effort per i preflight
    (suggerimento turbo + idoneità modello), mai fatale."""
    exe = shutil.which("ffprobe")
    if not exe or not path:
        return None
    try:
        out = subprocess.run(  # noqa: S603 — exe validato da shutil.which, args fissi
            [exe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        val = out.stdout.strip()
        return float(val) if val else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def to_wav_16k_mono(src_path: str, dst_path: str) -> float:
    """Converte qualunque formato in WAV 16kHz mono. Ritorna la durata in secondi."""
    check_ffmpeg()
    try:
        audio = AudioSegment.from_file(src_path)
    except CouldntDecodeError as e:
        raise AudioConversionError(src_path, e) from e
    audio = audio.set_channels(1).set_frame_rate(16000)
    audio.export(dst_path, format="wav")
    return len(audio) / 1000.0
