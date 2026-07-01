"""B1 — il wheel deve includere il desktop host (app/) + il frontend buildato (frontend/dist
→ app/_webdist) ed esporre il comando `vokari-app`. Senza, l'app non è installabile via
Homebrew formula / py2app (Fase B). Un guard di config veloce + un build-test reale (slow)."""

import shutil
import subprocess
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_packages_desktop_host():
    """Guard di config (veloce): pyproject impacchetta app/, espone vokari-app e include il dist.

    Il frontend è incluso via build-hook (hatch_build.py) invece che force-include statico,
    così `uv sync`/CI non falliscono senza frontend/dist buildato. L'inclusione reale nel wheel
    è verificata da test_wheel_includes_app_and_webdist (build vero)."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = data["project"]["scripts"]
    assert scripts.get("vokari-app") == "app.main:main"
    wheel = data["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert "app" in wheel["packages"]
    assert wheel["hooks"]["custom"]["path"] == "hatch_build.py"


@pytest.mark.slow
def test_wheel_includes_app_and_webdist(tmp_path):
    """Build reale del wheel + ispezione contenuto (la prova vera: hatchling onora la config)."""
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        pytest.skip("frontend/dist mancante: esegui 'cd frontend && pnpm build'")
    if shutil.which("uv") is None:
        pytest.skip("uv non disponibile")
    out = tmp_path / "wheelout"
    subprocess.run(["uv", "build", "--wheel", "-o", str(out)], cwd=ROOT, check=True, capture_output=True)
    wheels = list(out.glob("vokari-*.whl"))
    assert wheels, "nessun wheel prodotto"
    with zipfile.ZipFile(wheels[0]) as z:
        names = z.namelist()
    assert "app/main.py" in names, "app/main.py mancante nel wheel"
    assert "app/_webdist/index.html" in names, "frontend/dist non incluso come app/_webdist"
