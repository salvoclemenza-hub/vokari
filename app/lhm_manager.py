"""Gestione LibreHardwareMonitor integrato in VOKARI.

LHM espone i sensori hardware (temperatura CPU, ventole) via WMI nella
namespace root/LibreHardwareMonitor. Richiede una conferma UAC al primo avvio
(installazione del driver kernel); le letture successive da VOKARI non
richiedono admin.
"""

from __future__ import annotations

import json
import subprocess
import urllib.request
import zipfile
from pathlib import Path

_LHM_SUBDIR = Path("tools") / "lhm"
_LHM_EXE = "LibreHardwareMonitor.exe"
_GH_API = "https://api.github.com/repos/LibreHardwareMonitor/LibreHardwareMonitor/releases/latest"
_NO_WIN = 0x08000000  # CREATE_NO_WINDOW


def lhm_dir(data_dir: Path) -> Path:
    return data_dir / _LHM_SUBDIR


def lhm_exe(data_dir: Path) -> Path:
    return lhm_dir(data_dir) / _LHM_EXE


def is_installed(data_dir: Path) -> bool:
    return lhm_exe(data_dir).is_file()


def is_running() -> bool:
    """True se LHM è in esecuzione e il namespace WMI root/LibreHardwareMonitor ha dati."""
    try:
        ps = (
            "$s=Get-CimInstance -Namespace root/LibreHardwareMonitor -ClassName Sensor"
            " -ErrorAction SilentlyContinue;"
            "if($s){'yes'}else{'no'}"
        )
        r = subprocess.run(  # noqa: S603 — powershell fisso, input non controllato dall'utente
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=_NO_WIN,
        )
        return r.stdout.strip() == "yes"
    except Exception:
        return False


def _get_zip_url() -> str:
    req = urllib.request.Request(_GH_API, headers={"User-Agent": "VOKARI/1.0"})  # noqa: S310 — URL GitHub API hardcoded
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        data = json.loads(resp.read())
    for asset in data.get("assets", []):
        name: str = asset.get("name", "")
        if name.lower().endswith(".zip") and "librehardwaremonitor" in name.lower():
            return asset["browser_download_url"]
    raise RuntimeError("nessun ZIP trovato nella release LHM su GitHub")


def download(data_dir: Path, on_progress=None) -> None:
    """Scarica ed estrae LHM in data_dir/tools/lhm/. on_progress(pct 0..1) opzionale."""
    url = _get_zip_url()
    d = lhm_dir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    zip_path = d / "_lhm_download.zip"

    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 — URL GitHub releases, validato da _get_zip_url
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(zip_path, "wb") as f:
            while chunk := resp.read(65536):
                f.write(chunk)
                done += len(chunk)
                if on_progress and total:
                    on_progress(done / total)

    with zipfile.ZipFile(zip_path) as z:
        members = z.namelist()
        # Appiattisce una eventuale subdirectory radice (es. "LHM-v0.9.4/LibreHardwareMonitor.exe")
        root_dirs = {m.split("/")[0] for m in members if "/" in m}
        strip = (root_dirs.pop() + "/") if len(root_dirs) == 1 else ""
        for member in members:
            rel = member[len(strip) :] if (strip and member.startswith(strip)) else member
            if not rel or rel.endswith("/"):
                continue
            target = d / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())
    zip_path.unlink(missing_ok=True)


def start(data_dir: Path) -> bool:
    """Avvia LHM con elevazione admin (mostra finestra UAC). Ritorna True se lanciato."""
    import ctypes
    import sys

    if not sys.platform.startswith("win"):
        return False
    exe = str(lhm_exe(data_dir))
    wd = str(lhm_dir(data_dir))
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            exe,
            None,
            wd,
            7,  # 7 = SW_SHOWMINNOACTIVE
        )
        return int(ret) > 32
    except Exception:
        return False


def stop() -> None:
    """Termina tutti i processi LibreHardwareMonitor.exe."""
    try:
        subprocess.run(  # noqa: S603 — taskkill su eseguibile noto _LHM_EXE
            ["taskkill", "/F", "/IM", _LHM_EXE],  # noqa: S607
            capture_output=True,
            creationflags=_NO_WIN,
        )
    except Exception:  # noqa: S110 — taskkill può fallire (processo non avviato): ok
        pass


def uninstall(data_dir: Path) -> None:
    """Ferma LHM e rimuove i file estratti."""
    import shutil

    stop()
    shutil.rmtree(lhm_dir(data_dir), ignore_errors=True)
