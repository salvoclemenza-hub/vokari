from pathlib import Path

import pytest
from typer.testing import CliRunner

from vokari import __version__
from vokari import settings as st
from vokari.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    store = {}
    monkeypatch.setattr(st.keyring, "set_password", lambda s, k, v: store.__setitem__((s, k), v))
    monkeypatch.setattr(st.keyring, "get_password", lambda s, k: store.get((s, k)))


def test_version_flag():
    r = runner.invoke(app, ["--version"])
    assert r.exit_code == 0
    assert __version__ in r.stdout


def test_config_show_defaults():
    r = runner.invoke(app, ["config", "show"])
    assert r.exit_code == 0
    assert "whisper_model = large-v3-turbo" in r.stdout
    assert "anthropic_api_key = (non impostata)" in r.stdout


def test_config_set_roundtrip():
    assert runner.invoke(app, ["config", "set", "whisper_model", "large-v3"]).exit_code == 0
    r = runner.invoke(app, ["config", "show"])
    assert "whisper_model = large-v3" in r.stdout


def test_config_set_unknown_key_errors():
    r = runner.invoke(app, ["config", "set", "nope", "x"])
    assert r.exit_code == 1


def test_config_set_api_key_goes_to_keyring():
    runner.invoke(app, ["config", "set", "anthropic_api_key", "sk-ant-xyz"])
    r = runner.invoke(app, ["config", "show"])
    assert "anthropic_api_key = (impostata)" in r.stdout


# --- M2: transcribe + models list ---
from vokari.transcribe import models as models_mod
from vokari.transcribe import whisper as whisper_mod


def test_transcribe_writes_transcript_txt(tmp_path, monkeypatch):
    audio = tmp_path / "meeting.m4a"
    audio.write_bytes(b"fake")
    monkeypatch.setattr(
        whisper_mod,
        "transcribe",
        lambda src, *, model, language: {"text": "ciao mondo", "segments": [], "model": model},
    )
    r = runner.invoke(app, ["transcribe", str(audio)])
    assert r.exit_code == 0
    out = audio.with_suffix(".transcript.txt")
    assert out.exists()
    assert out.read_text(encoding="utf-8").strip() == "ciao mondo"
    assert str(out) in r.stdout


def test_transcribe_missing_file_errors():
    r = runner.invoke(app, ["transcribe", "non_esiste.wav"])
    assert r.exit_code == 1


def test_models_list_shows_catalog_with_state(monkeypatch):
    monkeypatch.setattr(models_mod, "is_downloaded", lambda name: name == "large-v3-turbo")
    r = runner.invoke(app, ["models", "list"])
    assert r.exit_code == 0
    assert "large-v3-turbo" in r.stdout
    assert "attivo" in r.stdout.lower()  # default + scaricato
    assert "small" in r.stdout


# --- M3: brief ---
def test_brief_generates_briefing_md(tmp_path, monkeypatch):
    import vokari.cli as climod

    audio = tmp_path / "riunione.m4a"
    audio.write_bytes(b"fake")

    monkeypatch.setattr(
        climod.whisper_mod,
        "transcribe",
        lambda src, *, model, language: {
            "text": "ciao",
            "model": model,
            "language": language,
            "source": src,
            "duration_s": 12.0,
        },
    )
    # niente vera chiamata LLM: analyzer e provider sostituiti
    monkeypatch.setattr(climod, "make_provider", lambda s: object())
    from vokari.analyze.schema import Analysis

    monkeypatch.setattr(
        climod.analyzer_mod,
        "analyze",
        lambda transcript, *, mode, provider, **kw: Analysis.model_validate({"meta": {"type": mode, "title": "X"}}),
    )

    r = runner.invoke(app, ["brief", str(audio)])
    assert r.exit_code == 0, r.output
    out = audio.with_suffix(".briefing.md")
    assert out.exists()
    md = out.read_text(encoding="utf-8")
    assert md.startswith("---\n") and "type: solo" in md
    assert str(out) in r.stdout


def test_brief_missing_file_errors():
    r = runner.invoke(app, ["brief", "nope.m4a"])
    assert r.exit_code == 1


# --- M4: rec ---
def test_rec_writes_wav_and_suggests_brief(tmp_path, monkeypatch):
    import vokari.cli as climod
    from vokari.audio.capture import CaptureResult

    out = tmp_path / "rec.wav"

    class FakeRecorder:
        def __init__(self, source, out_path, *, device=None):
            self.source = source
            self.out_path = out_path

        def start(self):
            pass

        def add_marker(self, label):
            return {"t_ms": 0, "label": label}

        def stop(self):
            Path(self.out_path).write_bytes(b"RIFFxxxx")
            return CaptureResult(self.out_path, 3.0, self.source, [])

    monkeypatch.setattr(climod.capture, "Recorder", FakeRecorder)
    r = runner.invoke(app, ["rec", "--source", "mic", "-o", str(out), "--seconds", "0"])
    assert r.exit_code == 0, r.output
    assert out.exists()
    assert str(out) in r.stdout
    assert "vokari brief" in r.stdout  # suggerisce il passo successivo


def test_rec_invalid_source_errors():
    r = runner.invoke(app, ["rec", "--source", "foo", "--seconds", "0"])
    assert r.exit_code == 1


def test_rec_list_devices(monkeypatch):
    import vokari.cli as climod

    monkeypatch.setattr(
        climod.capture,
        "list_input_devices",
        lambda: [{"index": 0, "name": "Mic A", "channels": 1, "samplerate": 44100}],
    )
    monkeypatch.setattr(
        climod.capture,
        "list_loopback_devices",
        lambda: [{"index": 5, "name": "Speakers", "channels": 2, "samplerate": 48000}],
    )
    r = runner.invoke(app, ["rec", "--list-devices"])
    assert r.exit_code == 0
    assert "Mic A" in r.stdout and "Speakers" in r.stdout


def test_rec_device_numeric_coerced_to_int(tmp_path, monkeypatch):
    import vokari.cli as climod
    from vokari.audio.capture import CaptureResult

    seen = {}

    class FakeRecorder:
        def __init__(self, source, out_path, *, device=None):
            seen["device"] = device
            self.out_path = out_path
            self.source = source

        def start(self):
            pass

        def stop(self):
            Path(self.out_path).write_bytes(b"RIFFxxxx")
            return CaptureResult(self.out_path, 1.0, self.source, [])

    monkeypatch.setattr(climod.capture, "Recorder", FakeRecorder)
    out = tmp_path / "r.wav"
    r = runner.invoke(app, ["rec", "-o", str(out), "--device", "2", "--seconds", "0"])
    assert r.exit_code == 0, r.output
    assert seen["device"] == 2 and isinstance(seen["device"], int)


def test_rec_device_name_kept_as_string(tmp_path, monkeypatch):
    import vokari.cli as climod
    from vokari.audio.capture import CaptureResult

    seen = {}

    class FakeRecorder:
        def __init__(self, source, out_path, *, device=None):
            seen["device"] = device
            self.out_path = out_path
            self.source = source

        def start(self):
            pass

        def stop(self):
            Path(self.out_path).write_bytes(b"RIFFxxxx")
            return CaptureResult(self.out_path, 1.0, self.source, [])

    monkeypatch.setattr(climod.capture, "Recorder", FakeRecorder)
    out = tmp_path / "r.wav"
    r = runner.invoke(app, ["rec", "-o", str(out), "--device", "Mic A", "--seconds", "0"])
    assert r.exit_code == 0, r.output
    assert seen["device"] == "Mic A"
