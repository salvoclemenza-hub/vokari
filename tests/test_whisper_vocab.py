# tests/test_whisper_vocab.py
from vokari.transcribe import whisper


def test_default_initial_prompt_is_neutral():
    base = whisper.build_initial_prompt("")
    low = base.lower()
    for term in ("vmm", "haccp", "ddt", "acciughe", "magazzino"):
        assert term not in low


def test_vocab_is_appended():
    p = whisper.build_initial_prompt("Magazzino alimentare: lotti VMM, MAC, HACCP")
    assert "VMM" in p and "HACCP" in p
