# tests/test_preflight.py
import sys

from app import preflight


def test_missing_prereqs_reports_ffmpeg(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(preflight.shutil, "which", lambda name: None)  # ffmpeg assente
    monkeypatch.setattr(preflight, "check_webkit", lambda: True)  # webkit presente
    assert "ffmpeg" in preflight.missing_prereqs()


def test_missing_prereqs_reports_webkit(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(preflight.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(preflight, "check_webkit", lambda: False)
    assert "webkit2gtk" in preflight.missing_prereqs()


def test_missing_prereqs_reports_portaudio_on_linux(monkeypatch):
    """Su Linux, se check_portaudio() fallisce, 'portaudio' è nella lista dei mancanti."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(preflight.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(preflight, "check_webkit", lambda: True)
    monkeypatch.setattr(preflight, "check_portaudio", lambda: False)
    assert "portaudio" in preflight.missing_prereqs()


def test_install_hint_mentions_apt():
    hint = preflight.install_hint(["ffmpeg", "webkit2gtk"])
    assert "apt" in hint and "ffmpeg" in hint


def test_install_hint_includes_portaudio_packages():
    """install_hint include libportaudio2 (apt), portaudio (dnf/pacman) quando portaudio manca."""
    hint = preflight.install_hint(["portaudio"])
    assert "libportaudio2" in hint  # apt
    assert hint.count("portaudio") >= 3  # apt+dnf+pacman
