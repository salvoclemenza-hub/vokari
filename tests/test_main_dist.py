# tests/test_main_dist.py
from pathlib import Path

from app import main


def test_find_dist_returns_existing_dev_path():
    # in sviluppo frontend/dist/index.html esiste dopo `pnpm build`
    p = main._find_dist()
    assert isinstance(p, Path)
    assert p.name == "index.html"


def test_find_dist_prefers_installed_when_dev_absent(monkeypatch, tmp_path):
    fake_app = tmp_path / "app"
    (fake_app / "_webdist").mkdir(parents=True)
    (fake_app / "_webdist" / "index.html").write_text("ok", encoding="utf-8")
    monkeypatch.setattr(main, "__file__", str(fake_app / "main.py"))
    # dev path (parent.parent/frontend/dist) non esiste sotto tmp_path → usa _webdist installato
    p = main._find_dist()
    assert p == fake_app / "_webdist" / "index.html"
