from pathlib import Path

from vokari import paths


def test_app_dirs_respects_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    d = paths.app_dirs()
    assert d.config == tmp_path / "config"
    assert d.data == tmp_path / "data"
    assert d.models == tmp_path / "cache" / "models"


def test_ensure_dirs_creates_all(monkeypatch, tmp_path):
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    d = paths.ensure_dirs()
    for p in (d.config, d.data, d.cache, d.models):
        assert Path(p).is_dir()
