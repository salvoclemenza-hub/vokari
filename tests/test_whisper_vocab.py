# tests/test_whisper_vocab.py
import shutil
import wave

import pytest

from vokari.transcribe import chunking, whisper


def test_default_initial_prompt_is_neutral():
    base = whisper.build_initial_prompt("")
    low = base.lower()
    for term in ("vmm", "haccp", "ddt", "acciughe", "magazzino"):
        assert term not in low


def test_vocab_is_appended():
    p = whisper.build_initial_prompt("Magazzino alimentare: lotti VMM, MAC, HACCP")
    assert "VMM" in p and "HACCP" in p


# --- Il vocabolario deve contare DAVVERO (2026-09-24) -------------------------
# Due bug gemelli: (1) la chiave di cache non includeva il vocabolario, quindi
# cambiarlo e ri-trascrivere lo stesso file restituiva la trascrizione vecchia;
# (2) il vocabolario viaggiava solo in `initial_prompt`, che esce dal contesto di
# Whisper dopo ~30s — su chunk da 600s era ininfluente per il 99% dell'audio.
# `hotwords` (faster-whisper >=1.1) viene invece ri-applicato a ogni finestra.


@pytest.fixture
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    monkeypatch.setattr(
        whisper.convert, "to_wav_16k_mono", lambda src, dst: (shutil.copy(src, dst), chunking.wav_duration(dst))[1]
    )
    # Mai rete/modelli reali nei test (ADR-061): senza questo la detection scarica da HF.
    monkeypatch.setattr(whisper, "detect_language", lambda wav, model: ("it", 0.99))


def _wav(path, seconds=1):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000 * seconds)
    return str(path)


def test_cache_key_changes_with_vocab(_isolate, tmp_path, monkeypatch):
    """Cambiare il vocabolario deve invalidare la cache: altrimenti l'utente
    aggiunge i nomi dei clienti in Impostazioni e non cambia nulla."""
    src = _wav(tmp_path / "a.wav", 2)
    calls = {"n": 0}

    def _fake_infer(audio, model_name, language, initial_prompt="", hotwords=""):
        calls["n"] += 1
        return [{"start": 0.0, "end": 1.0, "text": "uno"}]

    monkeypatch.setattr(whisper, "_transcribe_audio", _fake_infer)
    whisper.transcribe(src, model="small", language="it", vocab="Kamil, Weenat")
    whisper.transcribe(src, model="small", language="it", vocab="Kamil, Weenat")
    assert calls["n"] == 1  # stesso vocabolario = cache hit
    whisper.transcribe(src, model="small", language="it", vocab="Kamil, Weenat, Darkside")
    assert calls["n"] == 2  # vocabolario diverso = ri-trascrive


def test_stream_cache_key_changes_with_vocab(_isolate, tmp_path, monkeypatch):
    src = _wav(tmp_path / "b.wav", 2)
    calls = {"n": 0}

    def _fake_iter(audio, model_name, language, should_cancel=None, initial_prompt="", hotwords=""):
        calls["n"] += 1
        return iter([{"start": 0.0, "end": 1.0, "text": "uno"}])

    monkeypatch.setattr(whisper, "_iter_transcribe", _fake_iter)
    whisper.transcribe_stream(src, model="small", language="it", vocab="Kamil")
    whisper.transcribe_stream(src, model="small", language="it", vocab="Kamil")
    assert calls["n"] == 1
    whisper.transcribe_stream(src, model="small", language="it", vocab="Kamil, Weenat")
    assert calls["n"] == 2


class _FakeModel:
    def __init__(self):
        self.kwargs = {}

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        return iter([]), None


def test_hotwords_reach_the_model(_isolate, tmp_path, monkeypatch):
    """Il vocabolario deve arrivare come `hotwords`: `initial_prompt` da solo
    esce dal contesto dopo ~30s e non copre i chunk successivi."""
    fake = _FakeModel()
    monkeypatch.setattr(whisper, "_load_model", lambda name: fake)
    whisper._transcribe_audio(_wav(tmp_path / "c.wav"), "small", "it", initial_prompt="base", hotwords="Weenat, Kamil")
    assert fake.kwargs.get("hotwords") == "Weenat, Kamil"


def test_no_hotwords_when_no_vocab(_isolate, tmp_path, monkeypatch):
    """Senza vocabolario non si passa una stringa vuota al modello (None = assente)."""
    fake = _FakeModel()
    monkeypatch.setattr(whisper, "_load_model", lambda name: fake)
    whisper._transcribe_audio(_wav(tmp_path / "d.wav"), "small", "it")
    assert fake.kwargs.get("hotwords") is None


def test_stream_hotwords_reach_the_model(_isolate, tmp_path, monkeypatch):
    fake = _FakeModel()
    monkeypatch.setattr(whisper, "_load_model", lambda name: fake)
    list(whisper._iter_transcribe(_wav(tmp_path / "e.wav"), "small", "it", hotwords="Darkside"))
    assert fake.kwargs.get("hotwords") == "Darkside"
