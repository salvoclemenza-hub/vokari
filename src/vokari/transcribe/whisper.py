"""Trascrizione locale con faster-whisper + cache su hash audio.

`_load_model` e `_transcribe_audio` sono a livello modulo per essere mockate nei test
senza scaricare modelli né eseguire inferenza reale.
"""

import functools
import hashlib
import io
import json
import tempfile
import wave
from pathlib import Path

from vokari.audio import convert
from vokari.paths import ensure_dirs
from vokari.transcribe import chunking

_DEVICE = "cpu"  # spec §6: CTranslate2 non accelera su AMD -> solo CPU
_COMPUTE_TYPE = "int8"

# initial_prompt base (neutro): orienta Whisper su parlato generico. Il vocabolario di
# dominio dell'utente (settings.user_context) viene aggiunto da build_initial_prompt.
_INITIAL_PROMPT_BASE = "Trascrizione di una conversazione: riunione, brainstorming o nota a voce."


def build_initial_prompt(vocab: str = "") -> str:
    """initial_prompt per faster-whisper: base neutra + eventuale vocabolario utente
    (troncato per non sforare il contesto del modello di trascrizione)."""
    vocab = (vocab or "").strip()
    if not vocab:
        return _INITIAL_PROMPT_BASE
    return f"{_INITIAL_PROMPT_BASE} Termini ricorrenti: {vocab[:400]}"


def _is_wav_16k_mono(path: str) -> bool:
    """True se il file è già un WAV PCM16 16 kHz mono: in tal caso (tipico delle
    registrazioni, già normalizzate dal Recorder) si salta la ri-conversione ffmpeg (R4)."""
    try:
        with wave.open(path, "rb") as wf:
            return wf.getframerate() == 16000 and wf.getnchannels() == 1 and wf.getsampwidth() == 2
    except (wave.Error, OSError, EOFError):
        return False


def audio_hash(path: str) -> str:
    """sha256 (primi 16 hex) del contenuto del file: chiave di cache stabile."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


def build_text(segments: list[dict]) -> str:
    """Trascrizione lineare: testo dei segmenti unito da spazi (no speaker in v1)."""
    return " ".join(s["text"].strip() for s in segments if s["text"].strip())


@functools.lru_cache(maxsize=2)
def _load_model(model_name: str):
    # Cache per-nome: con file lunghi (più chunk) il modello si carica una sola volta,
    # non a ogni chunk. lru_cache espone .cache_clear() per i test/cambio modello.
    from faster_whisper import WhisperModel

    return WhisperModel(
        model_name,
        device=_DEVICE,
        compute_type=_COMPUTE_TYPE,
        download_root=str(ensure_dirs().models),
    )


def detect_language(wav_path: str, model_name: str) -> tuple[str, float]:
    """Rileva la lingua dominante dell'audio (1° segmento ≈30s) via faster-whisper.
    Modulo-level per essere mockata nei test. Ritorna (codice_lingua, probabilità 0..1).
    NON solleva mai al chiamante in produzione: il chiamante la avvolge in try/except
    (un fallimento di detection non deve far perdere la trascrizione)."""
    from faster_whisper.audio import decode_audio

    model = _load_model(model_name)
    audio = decode_audio(wav_path, sampling_rate=16000)
    lang, prob, _all = model.detect_language(audio)
    return lang, round(float(prob), 3)


def _safe_detect_language(wav_path: str, model_name: str) -> tuple[str, float]:
    """Wrapper tollerante: errore/modello assente → ('', 0.0). Non blocca mai la trascrizione."""
    try:
        return detect_language(wav_path, model_name)
    except Exception:
        return "", 0.0


def _transcribe_audio(audio, model_name: str, language: str, initial_prompt: str = "") -> list[dict]:
    """Inferenza reale su un audio (path o file-like). Ritorna [{start,end,text}]."""
    model = _load_model(model_name)
    lang = None if language == "auto" else language
    segments, _info = model.transcribe(
        audio,
        language=lang,
        beam_size=5,
        initial_prompt=initial_prompt or _INITIAL_PROMPT_BASE,
        # VAD: salta i tratti non-parlato (silenzi/musica/rumore). Senza, su file lunghi
        # faster-whisper macina i silenzi LENTISSIMO e ALLUCINA ("Grazie per la visione!",
        # "Sottotitoli a cura di…") → percepito come "trascrizione bloccata a metà".
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    return [
        {"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip()} for s in segments if s.text.strip()
    ]


def _cache_path(key: str) -> Path:
    d = ensure_dirs().cache / "transcripts"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.json"


def _iter_transcribe(audio, model_name: str, language: str, should_cancel=None, initial_prompt: str = ""):
    """Come _transcribe_audio ma yield-a i segmenti man mano (per lo streaming).
    Se `should_cancel()` diventa vero, interrompe subito (chiude il generatore faster-whisper)."""
    model = _load_model(model_name)
    lang = None if language == "auto" else language
    segments, _info = model.transcribe(
        audio,
        language=lang,
        beam_size=5,
        initial_prompt=initial_prompt or _INITIAL_PROMPT_BASE,
        # VAD: salta i tratti non-parlato (silenzi/musica/rumore). Senza, su file lunghi
        # faster-whisper macina i silenzi LENTISSIMO e ALLUCINA ("Grazie per la visione!",
        # "Sottotitoli a cura di…") → percepito come "trascrizione bloccata a metà".
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    for s in segments:
        if should_cancel is not None and should_cancel():
            return
        if s.text.strip():
            yield {"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip()}


def transcribe_stream(
    source_path: str, *, model: str, language: str, on_segment=None, should_cancel=None, vocab: str = ""
) -> dict:
    """Come transcribe ma invoca on_segment(pct, text_so_far, segment_text) ad ogni
    segmento. `should_cancel` (callable→bool) interrompe la trascrizione tra un segmento
    e l'altro. Cache identica a transcribe; su cache hit emette un singolo evento al 100%.
    Se cancellato a metà NON scrive cache (eviterebbe di cachare una trascrizione parziale)."""
    key = f"{audio_hash(source_path)}-{model}-{language}"
    cache = _cache_path(key)
    if cache.exists():
        result = json.loads(cache.read_text(encoding="utf-8"))
        if on_segment:
            on_segment(1.0, result["text"], result["text"], from_cache=True)
        result["from_cache"] = True
        return result

    initial_prompt = build_initial_prompt(vocab)
    detected_language: str = ""
    language_probability: float = 0.0
    with tempfile.TemporaryDirectory() as td:
        if _is_wav_16k_mono(source_path):
            wav = source_path  # già 16k mono (registrazione): no ri-conversione ffmpeg (R4)
        else:
            wav = str(Path(td) / "norm.wav")
            convert.to_wav_16k_mono(source_path, wav)
        duration = chunking.wav_duration(wav)
        detected_language, language_probability = _safe_detect_language(wav, model)
        segments: list[dict] = []

        def _emit(seg: dict) -> None:
            if on_segment:
                pct = min(1.0, seg["end"] / duration) if duration > 0 else 1.0
                on_segment(pct, build_text(segments), seg["text"])

        if duration <= chunking.CHUNK_DURATION_S:
            for seg in _iter_transcribe(
                wav, model, language, should_cancel=should_cancel, initial_prompt=initial_prompt
            ):
                segments.append(seg)
                _emit(seg)
        else:
            for chunk in chunking.split_wav(wav, chunking.CHUNK_DURATION_S):
                if should_cancel is not None and should_cancel():
                    break
                for seg in _iter_transcribe(
                    io.BytesIO(chunk.data), model, language, should_cancel=should_cancel, initial_prompt=initial_prompt
                ):
                    seg = chunking.apply_offset([seg], chunk.offset_s)[0]
                    # Dedup overlap (L17): tieni il segmento solo se cade nella finestra di
                    # questo chunk; la zona di sovrapposizione appartiene a un solo chunk.
                    if not (chunk.accept_lo <= seg["start"] < chunk.accept_hi):
                        continue
                    segments.append(seg)
                    _emit(seg)

    if should_cancel is not None and should_cancel():
        return {
            "source": source_path,
            "model": model,
            "language": language,
            "detected_language": detected_language,
            "language_probability": language_probability,
            "duration_s": round(duration, 2),
            "segments": segments,
            "text": build_text(segments),
            "cancelled": True,
        }

    result = {
        "source": source_path,
        "model": model,
        "language": language,
        "detected_language": detected_language,
        "language_probability": language_probability,
        "duration_s": round(duration, 2),
        "segments": segments,
        "text": build_text(segments),
    }
    cache.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def transcribe(source_path: str, *, model: str, language: str, vocab: str = "") -> dict:
    """Trascrive `source_path`. Cache su (hash, model, language). Ritorna il dict risultato."""
    key = f"{audio_hash(source_path)}-{model}-{language}"
    cache = _cache_path(key)
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    # Normalizza a WAV 16k mono in un file temporaneo (salta se già 16k mono, R4)
    initial_prompt = build_initial_prompt(vocab)
    detected_language: str = ""
    language_probability: float = 0.0
    with tempfile.TemporaryDirectory() as td:
        if _is_wav_16k_mono(source_path):
            wav = source_path
        else:
            wav = str(Path(td) / "norm.wav")
            convert.to_wav_16k_mono(source_path, wav)
        duration = chunking.wav_duration(wav)
        detected_language, language_probability = _safe_detect_language(wav, model)

        segments: list[dict] = []
        if duration <= chunking.CHUNK_DURATION_S:
            segments = _transcribe_audio(wav, model, language, initial_prompt=initial_prompt)  # path diretto (R3)
        else:
            for chunk in chunking.split_wav(wav, chunking.CHUNK_DURATION_S):
                segs = chunking.apply_offset(
                    _transcribe_audio(io.BytesIO(chunk.data), model, language, initial_prompt=initial_prompt),
                    chunk.offset_s,
                )
                # Dedup overlap (L17): la zona di sovrapposizione appartiene a un solo chunk.
                segments.extend(s for s in segs if chunk.accept_lo <= s["start"] < chunk.accept_hi)

    result = {
        "source": source_path,
        "model": model,
        "language": language,
        "detected_language": detected_language,
        "language_probability": language_probability,
        "duration_s": round(duration, 2),
        "segments": segments,
        "text": build_text(segments),
    }
    cache.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
