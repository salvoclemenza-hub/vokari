"""Anteprima live della dettatura: ricampiona i blocchi del microfono a 16k mono float32
(interpolazione lineare numpy, qualità bozza) e li trascrive a finestre con un modello
piccolo durante la registrazione. La trascrizione definitiva resta quella a fine Stop."""

import threading

import numpy as np


def resample_to_16k_f32(mono_int16: np.ndarray, src_rate: int) -> np.ndarray:
    """Ricampiona un array int16 mono a 16 kHz float32 normalizzato [-1,1].
    Interpolazione lineare (no anti-alias): sufficiente per una bozza di trascrizione."""
    x = np.asarray(mono_int16).reshape(-1)
    if x.size == 0:
        return np.zeros(0, dtype=np.float32)
    if src_rate == 16000:
        return x.astype(np.float32) / 32768.0
    n_out = round(x.size * 16000 / src_rate)
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    src_idx = np.linspace(0.0, x.size - 1, n_out)
    res = np.interp(src_idx, np.arange(x.size), x.astype(np.float32))
    return (res / 32768.0).astype(np.float32)


_LIVE_BEAM = 1  # bozza veloce: beam ridotto
_SILENCE_DBFS = -45.0  # soglia RMS sotto cui la finestra è "silenzio": NON trascrivere
# (Whisper allucina testo — es. 找找找 — sul silenzio, A3).
# Volutamente più aggressiva del gate cattura (capture._SILENT_DBFS
# = -50): qui la finestra è corta e l'anteprima è solo una bozza, meglio
# saltare qualche borderline che mostrare allucinazioni.


def _rms_dbfs(samples_f32: np.ndarray) -> float:
    """Livello RMS di un blocco float32 [-1,1] in dBFS. -inf-safe; ~-120 per blocco vuoto."""
    if samples_f32.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(samples_f32.astype(np.float32) ** 2)))
    return 20.0 * float(np.log10(rms + 1e-10))


def _transcribe_array(samples: np.ndarray, model_name: str, language: str) -> str:
    """Trascrive un array float32 16k con il modello piccolo. Import locale di whisper
    per non caricare faster-whisper finché non serve."""
    from vokari.transcribe import whisper as whisper_mod

    model = whisper_mod._load_model(model_name)
    lang = None if language == "auto" else language
    segments, _info = model.transcribe(samples, language=lang, beam_size=_LIVE_BEAM)
    return " ".join(s.text.strip() for s in segments if s.text.strip())


class LiveTranscriber:
    """Trascrive in background, a finestre, l'audio alimentato via feed(). Emette testo
    cumulativo via on_text. Tollerante: un errore (modello assente/inferenza) disattiva
    l'anteprima senza toccare la registrazione."""

    def __init__(
        self, *, model_name: str, on_text, language: str = "auto", interval_s: float = 6.0, min_window_s: float = 4.0
    ):
        self.model_name = model_name
        self.on_text = on_text
        self.language = language
        self.interval_s = interval_s
        self.min_window_s = min_window_s
        self._buf: list[np.ndarray] = []
        self._rate: int | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._text_parts: list[str] = []
        # Event (non bool): scritto dal thread _loop, letto dal thread di cattura in feed().
        self._disabled = threading.Event()

    def feed(self, mono_int16: np.ndarray, rate: int) -> None:
        if self._disabled.is_set():
            return
        with self._lock:
            self._rate = rate
            self._buf.append(np.asarray(mono_int16).reshape(-1).copy())

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _drain(self) -> tuple[np.ndarray, int] | None:
        with self._lock:
            if not self._buf or self._rate is None:
                return None
            chunk = np.concatenate(self._buf)
            rate = self._rate
            self._buf = []
        return chunk, rate

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._stop.wait(self.interval_s):
                break
            drained = self._drain()
            if drained is None:
                continue
            chunk, rate = drained
            if chunk.size / rate < self.min_window_s:
                with self._lock:
                    self._buf.insert(0, chunk)
                continue
            try:
                samples = resample_to_16k_f32(chunk, rate)
                # A3: salta le finestre silenziose. Su silenzio Whisper non resta muto ma
                # ALLUCINA (caratteri cinesi, "Sottotitoli…", ecc.): meglio non emettere nulla.
                if _rms_dbfs(samples) < _SILENCE_DBFS:
                    continue
                text = _transcribe_array(samples, self.model_name, self.language)
                if text:
                    self._text_parts.append(text)
                    self.on_text(" ".join(self._text_parts))
            except Exception:
                self._disabled.set()
                return

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
