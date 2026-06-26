"""Test per app/ffmpeg_manager: scoperta della cartella ffmpeg/ bundlata e prepend al PATH.

Nessun ffmpeg reale viene invocato: si verifica solo la logica di PATH (idempotenza, no-op
senza eseguibile) e che la cartella bundlata sia il sibling `ffmpeg/` del package app/."""

import os
from pathlib import Path

import app.ffmpeg_manager as fm


def test_bundled_dir_is_sibling_of_app():
    # nel pacchetto: <root>/app/ e <root>/ffmpeg/ → bundled_dir è "<...>/ffmpeg" accanto ad app/
    assert fm.bundled_dir().name == "ffmpeg"
    assert fm.bundled_dir().parent == Path(fm.__file__).resolve().parent.parent


def test_add_bundled_to_path_prepends_once(monkeypatch, tmp_path):
    monkeypatch.setattr(fm, "bundled_dir", lambda: tmp_path)
    (tmp_path / fm._EXE_NAME).write_text("x")
    monkeypatch.setenv("PATH", "/usr/bin")
    fm.add_bundled_to_path()
    assert str(tmp_path) in os.environ["PATH"].split(os.pathsep)
    # idempotente: una seconda chiamata non ri-prepende
    before = os.environ["PATH"]
    fm.add_bundled_to_path()
    assert os.environ["PATH"] == before


def test_add_bundled_to_path_noop_without_exe(monkeypatch, tmp_path):
    monkeypatch.setattr(fm, "bundled_dir", lambda: tmp_path)
    monkeypatch.setenv("PATH", "/usr/bin")
    fm.add_bundled_to_path()  # nessun ffmpeg bundlato → no-op
    assert os.environ["PATH"] == "/usr/bin"
