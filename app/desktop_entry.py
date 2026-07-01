"""Voce di menu Linux (.desktop): fa comparire VOKARI nel menu applicazioni con icona.
pip non integra il desktop → l'utente lancia `vokari-app --install-desktop` una volta.
Documentazione manuale nel README per i casi non standard (spec Linux §Cross-cutting)."""

from __future__ import annotations

import shutil
from pathlib import Path

_ICON = Path(__file__).resolve().parent / "assets" / "vokari.png"


def install_desktop_entry() -> Path:
    """Scrive ~/.local/share/applications/vokari.desktop (user-scope, no root). Ritorna il path."""
    apps = Path.home() / ".local" / "share" / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    exe = shutil.which("vokari-app") or "vokari-app"
    icon = str(_ICON) if _ICON.exists() else "vokari"
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=VOKARI\n"
        "Comment=Voce in conoscenza strutturata, 100% in locale\n"
        f"Exec={exe}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Office;Utility;AudioVideo;\n"
        "StartupWMClass=VOKARI\n"
    )
    dest = apps / "vokari.desktop"
    dest.write_text(content, encoding="utf-8")
    return dest
