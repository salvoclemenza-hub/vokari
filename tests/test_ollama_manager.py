"""Test per app/ollama_manager: risoluzione eseguibile, PATH, ensure_running (logica pura).

La rete (download dello ZIP) e i subprocess (`ollama serve`) NON vengono toccati: si verifica
solo la logica di selezione/avvio con `is_up`/`exe_path` mockati."""

import os

import app.ollama_manager as om


def test_exe_path_prefers_system(monkeypatch, tmp_path):
    monkeypatch.setattr(om.shutil, "which", lambda n: "C:/sys/ollama.exe")
    assert om.exe_path(tmp_path) == "C:/sys/ollama.exe"
    assert om.is_installed(tmp_path) is True


def test_exe_path_falls_back_to_bundled(monkeypatch, tmp_path):
    monkeypatch.setattr(om.shutil, "which", lambda n: None)
    # senza eseguibile: non installato
    assert om.exe_path(tmp_path) is None
    assert om.is_installed(tmp_path) is False
    # crea la copia bundled → viene trovata
    d = om.ollama_dir(tmp_path)
    d.mkdir(parents=True)
    exe = d / om._EXE_NAME
    exe.write_text("x")
    assert om.exe_path(tmp_path) == str(exe)
    assert om.is_installed(tmp_path) is True


def test_host_from_endpoint():
    assert om._host_from_endpoint("http://localhost:11434") == "localhost:11434"
    assert om._host_from_endpoint("http://127.0.0.1:11434/") == "127.0.0.1:11434"
    assert om._host_from_endpoint("https://host:1") == "host:1"


def test_add_bundled_to_path_prepends_once(monkeypatch, tmp_path):
    d = om.ollama_dir(tmp_path)
    d.mkdir(parents=True)
    (d / om._EXE_NAME).write_text("x")
    monkeypatch.setenv("PATH", "/usr/bin")
    om.add_bundled_to_path(tmp_path)
    assert str(d) in os.environ["PATH"].split(os.pathsep)
    # idempotente: una seconda chiamata non ri-prepende
    before = os.environ["PATH"]
    om.add_bundled_to_path(tmp_path)
    assert os.environ["PATH"] == before


def test_add_bundled_to_path_noop_without_exe(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", "/usr/bin")
    om.add_bundled_to_path(tmp_path)  # nessun bundled exe → no-op
    assert os.environ["PATH"] == "/usr/bin"


def test_ensure_running_already_up(monkeypatch, tmp_path):
    monkeypatch.setattr(om, "is_up", lambda e: True)
    assert om.ensure_running(tmp_path, "http://localhost:11434") is True


def test_ensure_running_missing_no_install(monkeypatch, tmp_path):
    monkeypatch.setattr(om, "is_up", lambda e: False)
    monkeypatch.setattr(om, "is_installed", lambda d: False)
    # senza install_if_missing non scarica e ritorna False (niente download in test)
    assert om.ensure_running(tmp_path, "http://localhost:11434", install_if_missing=False) is False


def test_start_true_if_already_up(monkeypatch, tmp_path):
    monkeypatch.setattr(om, "is_up", lambda e: True)
    assert om.start(tmp_path, "http://localhost:11434") is True


def test_start_false_if_not_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(om, "is_up", lambda e: False)
    monkeypatch.setattr(om, "exe_path", lambda d: None)
    assert om.start(tmp_path, "http://localhost:11434") is False
