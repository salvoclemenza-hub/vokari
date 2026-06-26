"""Rende visibile a VOKARI l'ffmpeg/ffprobe bundlato nel pacchetto distribuibile.

Nel pacchetto (ZIP → %LOCALAPPDATA%\\VOKARI) ffmpeg.exe/ffprobe.exe stanno in `<root>/ffmpeg/`
accanto a `app/` e `vokari/`. Il motore li cerca via `shutil.which` (vedi `audio/convert.py`):
prependendo quella cartella al PATH del processo, `shutil.which("ffmpeg")` li trova **senza che
il launcher debba toccare il PATH** — così basta un collegamento `.lnk` a `pythonw.exe`, niente
wrapper `.vbs`/`.bat` (fragili/oscurati su Windows). In sviluppo `<root>/ffmpeg/` non esiste →
no-op (si usa l'ffmpeg di sistema). Specchio di `ollama_manager.add_bundled_to_path`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_EXE_NAME = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"


def bundled_dir() -> Path:
    """Cartella ffmpeg/ del pacchetto: accanto al package app/ (cioè <root install>/ffmpeg)."""
    # app/ffmpeg_manager.py → parent = app/ → parent.parent = <root install>
    return Path(__file__).resolve().parent.parent / "ffmpeg"


def add_bundled_to_path() -> None:
    """Prepende `<root>/ffmpeg` al PATH del processo se contiene ffmpeg. Idempotente; no-op se assente."""
    d = bundled_dir()
    if not (d / _EXE_NAME).is_file():
        return
    ds = str(d)
    cur = os.environ.get("PATH", "")
    if ds not in cur.split(os.pathsep):
        os.environ["PATH"] = ds + os.pathsep + cur
