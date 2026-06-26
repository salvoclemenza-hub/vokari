"""Test per app/lhm_manager: stato install + gate policy Store (niente auto-download in MSIX).

La rete (download dello ZIP da GitHub) NON viene toccata: si verifica solo la logica di
capability/guard con sys.platform e is_packaged mockati."""

import app.lhm_manager as lm
import app.runtime_env as rt
import pytest


def test_is_installed_false_without_exe(tmp_path):
    assert lm.is_installed(tmp_path) is False
    d = lm.lhm_dir(tmp_path)
    d.mkdir(parents=True)
    (d / lm._LHM_EXE).write_text("x")
    assert lm.is_installed(tmp_path) is True


# --- gate policy Store (MSIX): niente auto-download del binario LHM -------------


def test_is_packaged_false_in_test_env():
    """In test/dev (non MSIX) deve essere False ed essere un bool puro (fail-safe)."""
    rt.is_packaged.cache_clear()
    assert rt.is_packaged() is False


def test_can_auto_install_true_on_windows_unpackaged(monkeypatch):
    monkeypatch.setattr(lm.sys, "platform", "win32")
    monkeypatch.setattr("app.runtime_env.is_packaged", lambda: False)
    assert lm.can_auto_install() is True


def test_can_auto_install_false_when_packaged(monkeypatch):
    """In MSIX (build Store) NON auto-installiamo LHM anche se siamo su Windows."""
    monkeypatch.setattr(lm.sys, "platform", "win32")
    monkeypatch.setattr("app.runtime_env.is_packaged", lambda: True)
    assert lm.can_auto_install() is False


def test_download_packaged_raises_store_guidance(monkeypatch, tmp_path):
    """In MSIX download() non scarica: solleva guida all'install manuale (mai rete in test)."""
    monkeypatch.setattr(lm.sys, "platform", "win32")
    monkeypatch.setattr("app.runtime_env.is_packaged", lambda: True)
    with pytest.raises(RuntimeError, match="Store"):
        lm.download(tmp_path)
