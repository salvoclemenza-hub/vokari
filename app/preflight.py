"""Preflight prerequisiti di sistema (Linux): ffmpeg + binding WebKitGTK di pywebview.
Pip non installa binari di sistema: se mancano, diamo un messaggio chiaro con il comando di
install della distro invece di un traceback opaco all'avvio. Vedi spec Linux §3 e §Cross-cutting."""

from __future__ import annotations

import shutil
import sys


def check_webkit() -> bool:
    """True se il binding GTK WebKit2 (usato da pywebview su Linux) è importabile."""
    try:
        import gi

        for ver in ("4.1", "4.0"):
            try:
                gi.require_version("WebKit2", ver)
                return True
            except ValueError:
                continue
        return False
    except ImportError:
        return False


def check_portaudio() -> bool:
    """True se PortAudio (richiesto da sounddevice) è caricabile. Su Linux i wheel di
    sounddevice NON bundlano PortAudio → serve la lib di sistema (libportaudio2)."""
    try:
        from vokari.audio import capture

        capture._sd()
        return True
    except Exception:
        return False


def missing_prereqs() -> list[str]:
    """Prerequisiti di sistema mancanti per l'attuale piattaforma. Vuoto = tutto ok.
    ffmpeg serve ovunque; WebKitGTK e PortAudio solo su Linux."""
    missing: list[str] = []
    if shutil.which("ffmpeg") is None:
        missing.append("ffmpeg")
    if sys.platform.startswith("linux"):
        if not check_webkit():
            missing.append("webkit2gtk")
        if not check_portaudio():
            missing.append("portaudio")
    return missing


def install_hint(missing: list[str]) -> str:
    """Comando suggerito per installare i prerequisiti mancanti (distro principali)."""
    pkgs_apt = {"ffmpeg": "ffmpeg", "webkit2gtk": "python3-gi gir1.2-webkit2-4.1", "portaudio": "libportaudio2"}
    pkgs_dnf = {"ffmpeg": "ffmpeg", "webkit2gtk": "webkit2gtk4.1 python3-gobject", "portaudio": "portaudio"}
    pkgs_pac = {"ffmpeg": "ffmpeg", "webkit2gtk": "webkit2gtk python-gobject", "portaudio": "portaudio"}
    apt = " ".join(pkgs_apt[m] for m in missing if m in pkgs_apt)
    dnf = " ".join(pkgs_dnf[m] for m in missing if m in pkgs_dnf)
    pac = " ".join(pkgs_pac[m] for m in missing if m in pkgs_pac)
    return (
        "Prerequisiti di sistema mancanti: "
        + ", ".join(missing)
        + "\n  Debian/Ubuntu:  sudo apt install "
        + apt
        + "\n  Fedora:         sudo dnf install "
        + dnf
        + "\n  Arch:           sudo pacman -S "
        + pac
    )
