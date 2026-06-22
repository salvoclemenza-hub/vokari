import time

import numpy as np

from vokari.transcribe import live as L


def test_live_transcriber_skips_silent_windows(monkeypatch):
    """A3: una finestra di puro silenzio non deve essere trascritta (Whisper allucina
    'testo' — es. caratteri cinesi — sul silenzio). Il modello NON viene invocato e
    nessun testo viene emesso."""
    called = {"n": 0}

    def fake_transcribe_array(samples, model_name, language):
        called["n"] += 1
        return "allucinazione"

    monkeypatch.setattr(L, "_transcribe_array", fake_transcribe_array)

    texts = []
    lt = L.LiveTranscriber(model_name="base", on_text=lambda t: texts.append(t), interval_s=0.05, min_window_s=0.0)
    lt.start()
    lt.feed(np.zeros(16000, dtype=np.int16), 16000)  # 1s di silenzio assoluto
    time.sleep(0.12)
    lt.stop()
    assert called["n"] == 0, "il modello è stato invocato su una finestra silenziosa"
    assert not texts, "è stato emesso testo da una finestra silenziosa"


def test_live_transcriber_transcribes_audible_windows(monkeypatch):
    """Una finestra con segnale udibile viene trascritta normalmente (il gate non
    blocca l'audio reale)."""
    monkeypatch.setattr(L, "_transcribe_array", lambda s, m, lang: "ciao mondo")
    texts = []
    lt = L.LiveTranscriber(model_name="base", on_text=lambda t: texts.append(t), interval_s=0.05, min_window_s=0.0)
    lt.start()
    rng = np.random.default_rng(0)
    loud = (rng.standard_normal(16000) * 8000).astype(np.int16)  # rumore forte ~ -12 dBFS
    lt.feed(loud, 16000)
    time.sleep(0.12)
    lt.stop()
    assert texts and "ciao mondo" in texts[-1]


def test_live_transcriber_emits_cumulative_text(monkeypatch):
    calls = {"n": 0}

    def fake_transcribe_array(samples, model_name, language):
        calls["n"] += 1
        return f"pezzo{calls['n']}"

    monkeypatch.setattr(L, "_transcribe_array", fake_transcribe_array)

    texts = []
    lt = L.LiveTranscriber(model_name="base", on_text=lambda t: texts.append(t), interval_s=0.05, min_window_s=0.0)
    lt.start()
    rng = np.random.default_rng(1)
    loud = lambda: (rng.standard_normal(1600) * 8000).astype(np.int16)  # noqa: E731 — segnale udibile
    lt.feed(loud(), 16000)
    time.sleep(0.12)
    lt.feed(loud(), 16000)
    time.sleep(0.12)
    lt.stop()
    assert texts, "nessun testo emesso"
    assert "pezzo1" in texts[-1]
