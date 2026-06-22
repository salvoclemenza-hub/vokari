import shutil
import wave

import pytest

from vokari.audio import convert


def test_check_ffmpeg_raises_when_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="ffmpeg"):
        convert.check_ffmpeg()


def test_check_ffmpeg_ok_when_present(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ffmpeg")
    convert.check_ffmpeg()  # non solleva


@pytest.mark.slow
def test_to_wav_16k_mono(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg non disponibile")
    # genera un WAV stereo 44.1kHz di 1s di silenzio
    src = tmp_path / "in.wav"
    with wave.open(str(src), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x00\x00" * 2 * 44100)
    dst = tmp_path / "out.wav"
    dur = convert.to_wav_16k_mono(str(src), str(dst))
    assert abs(dur - 1.0) < 0.05
    with wave.open(str(dst), "rb") as r:
        assert r.getnchannels() == 1
        assert r.getframerate() == 16000


def test_to_wav_16k_mono_wraps_decode_error_as_audio_conversion_error(tmp_path):
    """File corrotto → AudioConversionError con path e causa originale."""
    from unittest.mock import patch

    import pydub.exceptions

    from vokari.audio.convert import AudioConversionError, to_wav_16k_mono

    bad_file = tmp_path / "bad.m4a"
    bad_file.write_bytes(b"not-audio")
    dst = str(tmp_path / "out.wav")

    with patch("vokari.audio.convert.shutil.which", return_value="/usr/bin/ffmpeg"):
        with patch(
            "vokari.audio.convert.AudioSegment.from_file",
            side_effect=pydub.exceptions.CouldntDecodeError("decode failed"),
        ):
            with pytest.raises(AudioConversionError) as exc_info:
                to_wav_16k_mono(str(bad_file), dst)

    assert str(bad_file) in str(exc_info.value)


def test_probe_duration_s_returns_none_without_ffprobe(monkeypatch):
    """probe_duration_s è best-effort: nessun ffprobe nel PATH → None (mai eccezione)."""
    monkeypatch.setattr(convert.shutil, "which", lambda name: None)
    assert convert.probe_duration_s("qualsiasi.m4a") is None
    assert convert.probe_duration_s("") is None


def test_probe_duration_s_parses_ffprobe_output(monkeypatch):
    """probe_duration_s legge i secondi dall'output di ffprobe (format=duration)."""
    monkeypatch.setattr(convert.shutil, "which", lambda name: "/usr/bin/ffprobe")

    class _R:
        stdout = "742.531000\n"

    monkeypatch.setattr(convert.subprocess, "run", lambda *a, **k: _R())
    assert convert.probe_duration_s("x.m4a") == 742.531


def test_probe_duration_s_handles_garbage_output(monkeypatch):
    """Output non numerico (file senza durata nota) → None, non crash."""
    monkeypatch.setattr(convert.shutil, "which", lambda name: "/usr/bin/ffprobe")

    class _R:
        stdout = "N/A\n"

    monkeypatch.setattr(convert.subprocess, "run", lambda *a, **k: _R())
    assert convert.probe_duration_s("x.m4a") is None


def test_audio_conversion_error_has_path_and_cause(tmp_path):
    """AudioConversionError espone .path e .__cause__."""
    from vokari.audio.convert import AudioConversionError

    cause = ValueError("decode failed")
    err = AudioConversionError(str(tmp_path / "audio.m4a"), cause)
    assert "audio.m4a" in str(err)
    assert err.__cause__ is cause
