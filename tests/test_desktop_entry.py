# tests/test_desktop_entry.py
from pathlib import Path

from app import desktop_entry


def test_install_desktop_entry_writes_file(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(desktop_entry.shutil, "which", lambda name: "/usr/local/bin/vokari-app")
    dest = desktop_entry.install_desktop_entry()
    assert dest == tmp_path / ".local" / "share" / "applications" / "vokari.desktop"
    content = dest.read_text(encoding="utf-8")
    assert "Name=VOKARI" in content
    assert "Exec=/usr/local/bin/vokari-app" in content
    assert "Type=Application" in content
