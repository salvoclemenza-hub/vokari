"""Cattura audio VOKARI: mic (sounddevice) + audio di sistema WASAPI loopback
(pyaudiowpatch) + mix. Strategia: cattura ogni sorgente al sample rate nativo, poi
normalizza a 16 kHz mono (riusa convert.to_wav_16k_mono di M1) e, per 'both', mixa i
due WAV 16 kHz mono. La logica di scrittura/mix è pura e testabile; l'I/O hardware è
isolato dietro _sd()/_pyaudio() (import lazy) e mockato nei test.
"""

import os
import shutil
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from vokari.audio import convert
from vokari.transcribe.chunking import wav_duration

SAMPLE_RATE = 16000


def write_pcm16_wav(samples: np.ndarray, path: str | Path, *, samplerate: int, channels: int) -> None:
    """Scrive un array int16 (mono 1-D o interleaved) in un WAV PCM a 16 bit."""
    arr = np.asarray(samples, dtype=np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(arr.tobytes())


def _read_wav_int16(path: str | Path) -> tuple[np.ndarray, int, int]:
    """Legge un WAV PCM16. Ritorna (array, samplerate, channels); array 1-D se mono."""
    with wave.open(str(path), "rb") as wf:
        if wf.getsampwidth() != 2:
            raise ValueError("Atteso WAV PCM a 16 bit.")
        rate = wf.getframerate()
        channels = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
    arr = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        arr = arr.reshape(-1, channels)
    return arr, rate, channels


def _to_mono(arr: np.ndarray, channels: int) -> np.ndarray:
    """Riduce a mono (media dei canali) un array letto da _read_wav_int16; ritorna int32."""
    if channels == 1 or arr.ndim == 1:
        return arr.reshape(-1).astype(np.int32)
    return arr.astype(np.int32).mean(axis=1).round().astype(np.int32)


def mix_wav_16k_mono(path_a: str, path_b: str, out_path: str) -> None:
    """Mixa due WAV 16 kHz mono (somma con clipping, pad al più lungo) in un WAV 16k mono."""
    a, ra, ca = _read_wav_int16(path_a)
    b, rb, cb = _read_wav_int16(path_b)
    if ra != SAMPLE_RATE or rb != SAMPLE_RATE:
        raise ValueError(f"Attesi WAV a {SAMPLE_RATE} Hz; ricevuti {ra} Hz e {rb} Hz.")
    a = _to_mono(a, ca)
    b = _to_mono(b, cb)
    n = max(len(a), len(b))
    a = np.pad(a, (0, n - len(a)))
    b = np.pad(b, (0, n - len(b)))
    mixed = np.clip(a + b, -32768, 32767).astype(np.int16)
    write_pcm16_wav(mixed, out_path, samplerate=SAMPLE_RATE, channels=1)


# --- L14: preflight spazio disco prima di una registrazione lunga ---
# La cattura scrive i WAV nativi IN STREAMING nella tempdir (vedi _capture_*_native): se il
# disco si riempie a metà, la lane finisce in _errors e l'audio si perde allo Stop. Stimiamo
# in anticipo i minuti registrabili nello spazio libero e avvisiamo/blocchiamo prima di partire.
#
# Byte-rate NATIVO per lane (worst-case, PRIMA della normalizzazione a 16k mono): ~48 kHz,
# 16 bit, fino a 2 canali = 192 KB/s. Stima ALTA di proposito: meglio promettere meno minuti
# del reale che far perdere una registrazione lunga.
_NATIVE_BYTES_PER_S_PER_LANE = 48000 * 2 * 2  # 192_000

# Soglie sui minuti di registrazione stimati nello spazio libero.
_DISK_CRITICAL_MINUTES = 2.0  # sotto: blocca (non basta nemmeno per una registrazione breve)
_DISK_LOW_MINUTES = 30.0  # sotto (ma >= critico): avvisa, registrazione comunque consentita


def _capture_byte_rate(source: str) -> int:
    """Byte/s stimati scritti su disco durante la cattura nativa. 'both' = mic+system insieme (2 lane)."""
    lanes = 2 if source == "both" else 1
    return _NATIVE_BYTES_PER_S_PER_LANE * lanes


def disk_free_bytes(path: str | Path | None = None) -> int:
    """Spazio libero (byte) sul volume di `path` (default: la tempdir, dove la cattura scrive in
    streaming). Risale all'antenato esistente più vicino se `path` non esiste ancora."""
    p = Path(path) if path is not None else Path(tempfile.gettempdir())
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(str(p)).free


def recording_minutes_left(source: str, path: str | Path | None = None) -> float:
    """Minuti di registrazione stimati nello spazio libero, alla sorgente data (stima conservativa)."""
    return disk_free_bytes(path) / _capture_byte_rate(source) / 60.0


def disk_preflight(source: str, path: str | Path | None = None) -> tuple[str, float]:
    """Verifica lo spazio disco PRIMA di registrare. Ritorna (severity, minuti_stimati):
    'critical' (blocca), 'low' (avvisa), 'ok'. Tollerante: un errore di lettura del disco →
    'ok' (un check fallito non deve MAI impedire una registrazione)."""
    try:
        minutes = recording_minutes_left(source, path)
    except OSError:
        return "ok", float("inf")
    if minutes < _DISK_CRITICAL_MINUTES:
        return "critical", minutes
    if minutes < _DISK_LOW_MINUTES:
        return "low", minutes
    return "ok", minutes


_BLOCK = 1024
_LEVEL_INTERVAL = 0.1  # secondi tra due emissioni di livello (anti-flood verso il JS)
_STOP_JOIN_TIMEOUT = 4.0  # max attesa per thread di cattura su stop() (evita Stop bloccato)
_IDLE_POLL_S = 0.01  # poll quando il loopback non ha frame (sistema muto): Stop reattivo


def _rms_db(samples: np.ndarray) -> float:
    """Livello RMS di un blocco int16 in dBFS (0 = fondo scala, molto negativo = silenzio).

    Indipendente dal numero di canali: la media è su tutti i campioni. Soglia a -120 dB
    per blocco vuoto / silenzio assoluto (evita log(0))."""
    if samples.size == 0:
        return -120.0
    x = samples.astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(x * x)))
    return 20.0 * float(np.log10(rms + 1e-10))


def _sd():
    """Importa sounddevice on-demand (PortAudio). Errore chiaro se assente."""
    try:
        import sounddevice as sd
    except OSError as e:  # PortAudio non disponibile
        raise RuntimeError(f"sounddevice/PortAudio non disponibile: {e}") from e
    except ImportError as e:
        raise RuntimeError("sounddevice non installato (uv add sounddevice).") from e
    return sd


def _pyaudio():
    """Importa pyaudiowpatch on-demand (solo Windows). Errore chiaro se assente."""
    try:
        import pyaudiowpatch as pyaudio
    except ImportError as e:
        raise RuntimeError("Cattura audio di sistema: richiede PyAudioWPatch (solo Windows).") from e
    return pyaudio


def system_audio_supported() -> bool:
    """True se la cattura dell'audio di sistema (loopback) è disponibile su questa piattaforma:
    - Windows: WASAPI loopback (pyaudiowpatch importabile);
    - Linux: device monitor (PipeWire/PulseAudio) presente;
    - macOS/altro: False in v1 (servirebbe BlackHole o ScreenCaptureKit).
    Tollerante: non instanzia hardware oltre la query dei device, un errore → False."""
    if sys.platform.startswith("win"):
        try:
            _pyaudio()
        except RuntimeError:
            return False
        return True
    if sys.platform.startswith("linux"):
        try:
            return _default_monitor_device() is not None
        except Exception:
            return False
    return False


def _capture_mic_native(out_path: str, *, stop_event, device=None, pause_event=None, on_level=None, on_audio=None):
    """Cattura il microfono al sample rate nativo finché stop_event non è settato.
    Mentre pause_event è settato i frame vengono letti ma SCARTATI (pausa).
    Se `on_level` è dato, lo chiama con il livello RMS in dBFS ~ogni _LEVEL_INTERVAL s.
    Se `on_audio` è dato, lo chiama con (mono_int16, rate) per ogni blocco non in pausa.
    Scrive un WAV PCM16 mono nativo. Ritorna (samplerate, channels)."""
    sd = _sd()
    info = sd.query_devices(device, "input")
    rate = int(info["default_samplerate"])
    channels = 1
    last_level = 0.0
    stream = sd.InputStream(samplerate=rate, channels=channels, dtype="int16", device=device, blocksize=_BLOCK)
    # Scrittura in streaming sul WAV nativo: evita di accumulare l'intera registrazione
    # grezza in RAM (su 'both'/registrazioni lunghe erano centinaia di MB). I frame
    # vengono scritti blocco per blocco; output byte-identico a prima (R1).
    wf = wave.open(out_path, "wb")
    wf.setnchannels(channels)
    wf.setsampwidth(2)
    wf.setframerate(rate)
    try:
        stream.start()
        while not stop_event.is_set():
            data, _ = stream.read(_BLOCK)
            if pause_event is not None and pause_event.is_set():
                continue
            wf.writeframes(data.tobytes())
            mono = np.asarray(data).reshape(-1)
            if on_audio is not None:
                on_audio(mono, rate)
            if on_level is not None:
                now = time.monotonic()
                if now - last_level >= _LEVEL_INTERVAL:
                    last_level = now
                    on_level(_rms_db(np.asarray(data)))
    finally:
        stream.stop()
        stream.close()
        wf.close()
    return rate, channels


def _capture_system_native(out_path: str, *, stop_event, device=None, pause_event=None, on_level=None, on_audio=None):
    """Cattura l'audio di sistema via WASAPI loopback finché stop_event non è settato.
    Mentre pause_event è settato i frame vengono letti ma SCARTATI (pausa).
    Se `on_level` è dato, lo chiama con il livello RMS in dBFS ~ogni _LEVEL_INTERVAL s.
    Se `on_audio` è dato, lo chiama con (mono_int16, rate) per ogni blocco non in pausa.
    Scrive un WAV PCM16 nativo (channels del device). Ritorna (samplerate, channels).
    `device` è ignorato (usa il loopback di default dell'uscita predefinita)."""
    pa = _pyaudio()
    p = pa.PyAudio()
    last_level = 0.0
    wf = None
    try:
        info = p.get_default_wasapi_loopback()
        rate = int(info["defaultSampleRate"])
        channels = int(info["maxInputChannels"])
        # Streaming write sul WAV nativo (vedi _capture_mic_native, R1): niente accumulo
        # dell'intero loopback grezzo in RAM.
        wf = wave.open(out_path, "wb")
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        stream = p.open(
            format=pa.paInt16,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=info["index"],
            frames_per_buffer=_BLOCK,
        )
        try:
            while not stop_event.is_set():
                # WASAPI loopback consegna frame SOLO mentre il sistema riproduce audio:
                # a sistema muto get_read_available() resta 0. Leggendo solo quando ci sono
                # almeno _BLOCK frame, il loop controlla stop_event ~ogni _IDLE_POLL_S → Stop
                # reattivo anche in silenzio (prima read() bloccava all'infinito).
                if stream.get_read_available() < _BLOCK:
                    time.sleep(_IDLE_POLL_S)
                    continue
                block = stream.read(_BLOCK, exception_on_overflow=False)
                if pause_event is not None and pause_event.is_set():
                    continue
                wf.writeframes(block)
                if on_audio is not None:
                    arr = np.frombuffer(block, dtype=np.int16)
                    if channels > 1:
                        arr = arr.reshape(-1, channels).astype(np.int32).mean(axis=1).astype(np.int16)
                    on_audio(arr, rate)
                if on_level is not None:
                    now = time.monotonic()
                    if now - last_level >= _LEVEL_INTERVAL:
                        last_level = now
                        on_level(_rms_db(np.frombuffer(block, dtype=np.int16)))
        finally:
            stream.stop_stream()
            stream.close()
    finally:
        p.terminate()
        if wf is not None:
            wf.close()
    return rate, channels


_SILENT_DBFS = -50.0  # sotto questo livello l'audio finale è "praticamente silenzioso" (A2)


def _wav_rms_dbfs(path: str | Path) -> float:
    """Livello RMS in dBFS dell'intero WAV (mono o multicanale). Best-effort: -120 se illeggibile."""
    try:
        arr, _rate, _ch = _read_wav_int16(path)
    except (wave.Error, OSError, ValueError, EOFError):
        return -120.0
    return _rms_db(np.asarray(arr).reshape(-1))


@dataclass
class CaptureResult:
    wav_path: str
    duration_s: float
    source: str  # sorgente EFFETTIVA (può differire dalla richiesta)
    markers: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)  # es. "system: ..." se 'both' è degradato a mic
    diagnostics: dict = field(default_factory=dict)  # livelli RMS per-lane + finale (A2, per debug log)


def _normalize(src_path: str, dst_path: str) -> None:
    """Porta un WAV nativo a 16 kHz mono (riusa la conversione ffmpeg di M1)."""
    convert.to_wav_16k_mono(src_path, dst_path)


class Recorder:
    """Orchestratore di cattura: avvia uno o due stream nativi in thread (uno per
    sorgente), su stop normalizza a 16k mono e (per 'both') mixa. Riusato dalla GUI in M6.
    Limite onesto v1: in 'both' i due stream partono in momenti vicini ma non
    sample-accurate; il mix tronca/padda alla lunghezza massima (allineamento ~best-effort).
    """

    def __init__(self, source: str, out_path: str, *, device=None, system_device=None, on_level=None, on_audio=None):
        if source not in ("mic", "system", "both"):
            raise ValueError(f"source non valida: {source!r} (usa mic|system|both)")
        self.source = source
        self.out_path = str(out_path)
        self._device = device
        self._system_device = system_device  # device monitor per la lane 'system' (Linux); None = autodetect
        self._on_level = on_level  # callback(lane: str, db: float) | None
        self._on_audio = on_audio  # callback(mono_int16: np.ndarray, rate: int) | None
        self._audio_lane: str | None = None  # lane preferita per on_audio (mic > altri)
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._threads: list[tuple[str, threading.Thread]] = []
        self._native: dict[str, Path] = {}
        self._errors: dict[str, Exception] = {}
        self._markers: list[dict] = []
        self._paused_total = 0.0  # secondi totali trascorsi in pausa (i frame in pausa sono scartati)
        self._paused_at: float | None = None  # monotonic di inizio pausa corrente, o None
        self._start_monotonic = None
        self._tmpdir: Path | None = None

    def _emit_level(self, lane: str, db: float) -> None:
        if self._on_level is None:
            return
        try:
            self._on_level(lane, db)
        except Exception:  # noqa: S110 — il livello è decorativo, non deve rompere la cattura
            pass

    def _system_capture_fn(self):
        """Funzione di cattura per la lane 'system': WASAPI loopback su Windows, cattura
        sounddevice (device monitor) altrove (Linux/PipeWire-Pulse)."""
        if sys.platform.startswith("win"):
            return _capture_system_native
        return _capture_mic_native

    def _resolve_device(self, name: str):
        """Device da passare alla lane `name`. La lane 'system' su Linux usa il device monitor
        esplicito (self._system_device) o, se assente, il primo monitor disponibile. Su Windows
        il loopback ignora il device. La lane 'mic' usa self._device."""
        if name == "system" and not sys.platform.startswith("win"):
            return self._system_device if self._system_device is not None else _default_monitor_device()
        return self._device

    def _run_capture(self, name, fn, native_path, device):
        kwargs = {"stop_event": self._stop, "device": device, "pause_event": self._pause}
        if self._on_level:
            kwargs["on_level"] = lambda db: self._emit_level(name, db)
        if self._on_audio is not None and name == self._audio_lane:
            kwargs["on_audio"] = self._on_audio
        try:
            fn(str(native_path), **kwargs)
        except Exception as e:
            self._errors[name] = e

    def start(self) -> None:
        self._start_monotonic = time.monotonic()
        self._paused_total = 0.0
        self._paused_at = None
        self._tmpdir = Path(tempfile.mkdtemp(prefix="vokari-rec-"))
        funcs = {"mic": _capture_mic_native, "system": self._system_capture_fn()}
        active = ["mic", "system"] if self.source == "both" else [self.source]
        self._audio_lane = "mic" if "mic" in active else active[0]
        for name in active:
            native = self._tmpdir / f"{name}_native.wav"
            self._native[name] = native
            t = threading.Thread(
                target=self._run_capture, args=(name, funcs[name], native, self._resolve_device(name)), daemon=True
            )
            self._threads.append((name, t))
            t.start()

    def add_marker(self, label: str) -> dict:
        """Aggiunge un marcatore al tempo di AUDIO trascorso da start() (esclude le pause:
        i frame in pausa sono scartati, quindi il wall-clock disallineerebbe il t_ms dalla
        posizione reale nell'audio finale). Se chiamato prima di start(), t_ms vale 0.
        Chiamato dal thread js-api (serializzato con pause/resume): nessun lock necessario."""
        base = self._start_monotonic if self._start_monotonic is not None else time.monotonic()
        now = time.monotonic()
        paused = self._paused_total + ((now - self._paused_at) if self._paused_at is not None else 0.0)
        t_ms = max(0, int((now - base - paused) * 1000))
        m = {"t_ms": t_ms, "label": label}
        self._markers.append(m)
        return m

    def update_marker(self, index: int, label: str) -> dict | None:
        """Aggiorna l'etichetta del marker `index` (editing inline lato UI). None se fuori range."""
        if 0 <= index < len(self._markers):
            self._markers[index]["label"] = label
            return self._markers[index]
        return None

    def pause(self) -> None:
        """Sospende l'accumulo dei frame (i thread continuano a leggere e scartano)."""
        if self._paused_at is None:
            self._paused_at = time.monotonic()
        self._pause.set()

    def resume(self) -> None:
        if self._paused_at is not None:
            self._paused_total += time.monotonic() - self._paused_at
            self._paused_at = None
        self._pause.clear()

    def is_paused(self) -> bool:
        return self._pause.is_set()

    def stop(self) -> CaptureResult:
        if self._tmpdir is None:
            raise RuntimeError("Nessuna registrazione attiva: chiama start() prima di stop().")
        self._stop.set()
        for name, t in self._threads:
            t.join(timeout=_STOP_JOIN_TIMEOUT)
            if t.is_alive():
                # Thread di cattura bloccato (tipico: loopback WASAPI di sistema senza audio
                # in riproduzione, stream.read() non ritorna): NON bloccare Stop all'infinito.
                # Segnala la sorgente come non terminata e procedi con le altre (fallback).
                self._errors.setdefault(name, RuntimeError("cattura non terminata in tempo (sorgente bloccata)"))
        warnings: list[str] = []
        try:
            # Normalizza solo le sorgenti catturate senza errore. Una sorgente fallita
            # NON deve far perdere l'intera registrazione: con 'both' si ripiega su
            # quella disponibile (di solito il microfono). Si solleva SOLO se non c'è
            # alcun audio utilizzabile.
            norm: dict[str, Path] = {}
            for name, native in self._native.items():
                if name in self._errors:
                    warnings.append(f"{name}: {self._errors[name]}")
                    continue
                try:
                    dst = self._tmpdir / f"{name}_16k.wav"
                    _normalize(str(native), str(dst))
                    norm[name] = dst
                except Exception as e:
                    warnings.append(f"{name}: normalizzazione fallita: {e}")
            if not norm:
                detail = "; ".join(warnings) if warnings else "nessun audio catturato"
                raise RuntimeError("Cattura fallita: " + detail)

            if self.source == "both" and "mic" in norm and "system" in norm:
                mix_wav_16k_mono(str(norm["mic"]), str(norm["system"]), self.out_path)
                effective = "both"
            else:
                effective = "mic" if "mic" in norm else next(iter(norm))
                shutil.copyfile(norm[effective], self.out_path)
                if self.source == "both":
                    warnings.append(f"audio di sistema non disponibile: registrato solo '{effective}'")
            duration = wav_duration(self.out_path)
            # A2 — diagnostica livelli: misura il RMS di ogni lane normalizzata e del file
            # finale. Serve a capire (dal debug log) perché una registrazione 'both' può
            # risultare muta nonostante una lane avesse audio (es. lane persa nel mix/fallback).
            diagnostics: dict = {"requested_source": self.source, "effective_source": effective}
            for name, p in norm.items():
                diagnostics[f"{name}_dbfs"] = round(_wav_rms_dbfs(p), 1)
            final_db = _wav_rms_dbfs(self.out_path)
            diagnostics["final_dbfs"] = round(final_db, 1)
            # Misura ANCHE le lane NATIVE (pre-normalizzazione) per le sorgenti il cui thread è
            # terminato (no race di lettura): distingue "lane muta già in cattura" da "lane persa
            # in normalizzazione/mix", e una durata nativa molto più corta dell'altra lane
            # smaschera il frame-drop del loopback (mix disallineato nel tempo). Le lane wedged
            # (in _errors) si saltano: il WAV nativo potrebbe essere ancora in scrittura.
            for name, native in self._native.items():
                if name in self._errors:
                    continue
                try:
                    diagnostics[f"{name}_native_dbfs"] = round(_wav_rms_dbfs(native), 1)
                    diagnostics[f"{name}_native_s"] = round(wav_duration(str(native)), 2)
                except (wave.Error, OSError, ValueError, EOFError):
                    pass
            # Se il risultato è quasi-silenzioso ma una lane aveva chiaramente segnale,
            # avvisa esplicitamente: meglio di un criptico "trascrizione vuota" più avanti.
            if final_db < _SILENT_DBFS:
                loud = [n for n, p in norm.items() if _wav_rms_dbfs(p) >= _SILENT_DBFS]
                if loud:
                    warnings.append(
                        "audio finale quasi silenzioso pur avendo segnale su "
                        f"{', '.join(loud)}: controlla i livelli delle sorgenti"
                    )
                else:
                    warnings.append("audio molto basso o assente: controlla microfono/uscita audio e i livelli")
        finally:
            self._dump_native_for_debug()
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            self._tmpdir = None
        return CaptureResult(self.out_path, duration, effective, list(self._markers), warnings, diagnostics)

    def _dump_native_for_debug(self) -> None:
        """Sotto VOKARI_DEBUG copia i WAV nativi per-lane nei log PRIMA che il tmpdir venga
        cancellato: permette di riascoltare ogni sorgente per diagnosticare un 'both' muto (A2).
        Best-effort: niente qui dentro deve mai rompere la chiusura della registrazione."""
        if os.environ.get("VOKARI_DEBUG", "").strip().lower() in ("", "0", "false", "no", "off"):
            return
        try:
            from vokari.paths import app_dirs

            dest = app_dirs().data / "logs"
            dest.mkdir(parents=True, exist_ok=True)
            stamp = int(time.time())
            for name, native in self._native.items():
                try:
                    if native.exists():
                        shutil.copyfile(native, dest / f"capture-{stamp}-{name}_native.wav")
                except OSError:
                    pass
        except OSError:
            pass


def sweep_orphan_tempdirs(max_age_s: float = 7200) -> int:
    """Rimuove le dir temporanee 'vokari-rec-*' più vecchie di `max_age_s` (registrazioni
    non finalizzate per un crash/chiusura imprevista). Il filtro per ETÀ è essenziale: senza,
    cancellerebbe la dir di una registrazione IN CORSO (race). Best-effort: niente qui dentro
    deve sollevare. Ritorna quante dir sono state rimosse. Chiamato all'avvio da main.py."""
    root = Path(tempfile.gettempdir())
    now = time.time()
    removed = 0
    try:
        for d in root.glob("vokari-rec-*"):
            try:
                if d.is_dir() and (now - d.stat().st_mtime) > max_age_s:
                    shutil.rmtree(d, ignore_errors=True)
                    removed += 1
            except OSError:
                pass
    except OSError:
        pass
    return removed


def list_input_devices() -> list[dict]:
    """Microfoni/ingressi disponibili: [{index, name, channels, samplerate}]."""
    sd = _sd()
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            out.append(
                {
                    "index": i,
                    "name": d["name"],
                    "channels": d["max_input_channels"],
                    "samplerate": int(d["default_samplerate"]),
                }
            )
    return out


def list_loopback_devices() -> list[dict]:
    """Dispositivi WASAPI loopback (audio di sistema) su Windows: [{index, name, channels, samplerate}]."""
    pa = _pyaudio()
    p = pa.PyAudio()
    out = []
    try:
        for d in p.get_loopback_device_info_generator():
            out.append(
                {
                    "index": d["index"],
                    "name": d["name"],
                    "channels": d["maxInputChannels"],
                    "samplerate": int(d["defaultSampleRate"]),
                }
            )
    finally:
        p.terminate()
    return out


def list_monitor_devices() -> list[dict]:
    """Sorgenti 'monitor' di sistema su Linux (PulseAudio/PipeWire): catturano l'audio in
    USCITA. Sono normali device di input il cui nome contiene 'monitor'. Speculare a
    list_loopback_devices() (Windows). [{index, name, channels, samplerate}]."""
    sd = _sd()
    out = []
    for i, d in enumerate(sd.query_devices()):
        name = str(d.get("name", ""))
        if d["max_input_channels"] > 0 and "monitor" in name.lower():
            out.append(
                {
                    "index": i,
                    "name": name,
                    "channels": d["max_input_channels"],
                    "samplerate": int(d["default_samplerate"]),
                }
            )
    return out


def _default_monitor_device() -> int | None:
    """Indice del primo device monitor disponibile (Linux), o None se nessuno/errore."""
    try:
        mons = list_monitor_devices()
    except RuntimeError:
        return None
    return mons[0]["index"] if mons else None
