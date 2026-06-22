import importlib.util
from pathlib import Path
from unittest.mock import patch


def _load():
    spec = importlib.util.spec_from_file_location("bump_version", Path("scripts/bump_version.py"))
    bv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bv)
    return bv


def test_bump_patch(tmp_path):
    pj = tmp_path / "pyproject.toml"
    pj.write_text('[project]\nname="vokari"\nversion = "0.1.0"\n')
    bv = _load()
    with patch.object(bv, "PYPROJECT", pj), patch("subprocess.run"):
        assert bv._current() == "0.1.0"
        assert bv._bump("patch") == "0.1.1"


def test_bump_minor_major(tmp_path):
    pj = tmp_path / "pyproject.toml"
    pj.write_text('[project]\nname="vokari"\nversion = "0.2.3"\n')
    bv = _load()
    with patch.object(bv, "PYPROJECT", pj):
        assert bv._bump("minor") == "0.3.0"
        assert bv._bump("major") == "1.0.0"
