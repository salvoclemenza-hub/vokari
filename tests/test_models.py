import pytest

from vokari import settings as st
from vokari.transcribe import models


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))


def test_catalog_has_expected_models():
    names = [m.name for m in models.CATALOG]
    assert names == ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]
    # nessun modello solo-EN nel default (spec §6)
    assert not any("distil" in n or n.endswith(".en") for n in names)


def test_default_model_is_marked_recommended():
    rec = [m for m in models.CATALOG if m.recommended]
    assert len(rec) == 1 and rec[0].name == "large-v3-turbo"


def test_is_downloaded_true_when_download_model_succeeds(monkeypatch):
    monkeypatch.setattr(models, "_download_model", lambda name, local_files_only, cache_dir: "/some/path")
    assert models.is_downloaded("small") is True


def test_is_downloaded_false_when_download_model_raises(monkeypatch):
    def _boom(name, local_files_only, cache_dir):
        raise FileNotFoundError("not cached")

    monkeypatch.setattr(models, "_download_model", _boom)
    assert models.is_downloaded("small") is False


def test_download_calls_download_model_with_cache_dir(monkeypatch, tmp_path):
    calls = {}

    def _fake(name, local_files_only, cache_dir):
        calls["name"] = name
        calls["cache_dir"] = cache_dir
        calls["local_files_only"] = local_files_only
        return str(tmp_path / "model")

    monkeypatch.setattr(models, "_download_model", _fake)
    models.download("large-v3")
    assert calls["name"] == "large-v3"
    assert calls["local_files_only"] is False
    assert "models" in calls["cache_dir"]  # punta alla dir cache/models di VOKARI


def test_is_downloaded_has_no_filesystem_side_effects(monkeypatch, tmp_path):
    # un controllo read-only non deve creare la dir dei modelli
    monkeypatch.setattr(models, "_download_model", lambda name, local_files_only, cache_dir: "/p")
    models.is_downloaded("small")
    assert not (tmp_path / "cache" / "models").exists()


def test_download_ensures_models_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(models, "_download_model", lambda name, local_files_only, cache_dir: "/p")
    models.download("small")
    assert (tmp_path / "cache" / "models").exists()


def test_is_downloaded_propagates_permission_error(monkeypatch, tmp_path):
    """PermissionError (cache corrotta / permessi disco) NON viene silenziato."""
    import vokari.transcribe.models as m

    monkeypatch.setattr(m, "_cache_dir", lambda: str(tmp_path))
    from unittest.mock import patch

    with patch("vokari.transcribe.models._download_model", side_effect=PermissionError("nope")):
        with pytest.raises(PermissionError):
            m.is_downloaded("small")


def test_state_active_downloaded_available(monkeypatch):
    s = st.Settings()  # whisper_model default = large-v3-turbo
    monkeypatch.setattr(models, "is_downloaded", lambda name: name in {"small", "large-v3-turbo"})
    assert models.state("large-v3-turbo", s) == "active"  # default + scaricato
    assert models.state("small", s) == "downloaded"
    assert models.state("large-v3", s) == "available"
