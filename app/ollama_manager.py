"""Gestione di Ollama integrata in VOKARI.

Obiettivo: l'utente non deve fare nulla a mano. VOKARI sa:
- **avviare** Ollama se è installato ma non in esecuzione (`start`/`ensure_running`);
- **installarlo** se manca, scaricando lo ZIP portabile ufficiale (`download`) — su Windows
  niente installer né UAC: tutto in `userData/tools/ollama/`, rimovibile;
- renderlo visibile al resto del motore prependendolo al PATH del processo
  (`add_bundled_to_path`) così anche `ollama_provider.ensure_available` (usato dalla pipeline)
  trova l'eseguibile bundled via `shutil.which`.

Su piattaforme diverse da Windows ci si appoggia a un'eventuale installazione di sistema
(`shutil.which("ollama")`); l'auto-installazione è offerta solo dove abbiamo uno ZIP portabile.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from vokari.llm.ollama_provider import is_up

_OLLAMA_SUBDIR = Path("tools") / "ollama"
_EXE_NAME = "ollama.exe" if sys.platform.startswith("win") else "ollama"
# ZIP portabile ufficiale (include il CLI + i runner): nessun installer, nessun admin.
# 'latest/download/<asset>' segue il redirect all'ultima release.
_WIN_ZIP_URL = "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip"
_NO_WIN = 0x08000000  # CREATE_NO_WINDOW
_DETACHED = 0x00000008  # DETACHED_PROCESS


def ollama_dir(data_dir: Path) -> Path:
    return data_dir / _OLLAMA_SUBDIR


def bundled_exe(data_dir: Path) -> Path:
    return ollama_dir(data_dir) / _EXE_NAME


def exe_path(data_dir: Path) -> str | None:
    """Eseguibile ollama da usare: prima quello di sistema (PATH), poi il bundled. None se assente."""
    sys_exe = shutil.which("ollama")
    if sys_exe:
        return sys_exe
    b = bundled_exe(data_dir)
    return str(b) if b.is_file() else None


def is_installed(data_dir: Path) -> bool:
    return exe_path(data_dir) is not None


def is_running(endpoint: str) -> bool:
    return is_up(endpoint)


def can_auto_install() -> bool:
    """True dove possiamo scaricare lo ZIP portabile di Ollama: Windows x64 E **non** in un
    pacchetto MSIX (build Store). Le policy Store vietano di scaricare+eseguire un binario di
    terze parti dall'app → in MSIX l'utente installa Ollama da sé (la UI lo guida); avviare un
    Ollama già installato resta consentito. Vedi runtime_env.is_packaged e ADR-046."""
    from app import runtime_env

    return sys.platform.startswith("win") and not runtime_env.is_packaged()


def add_bundled_to_path(data_dir: Path) -> None:
    """Rende l'ollama bundled visibile a shutil.which/subprocess prependendolo al PATH del processo.
    No-op se non c'è un eseguibile bundled. Idempotente."""
    d = ollama_dir(data_dir)
    if not (d / _EXE_NAME).is_file():
        return
    ds = str(d)
    cur = os.environ.get("PATH", "")
    if ds not in cur.split(os.pathsep):
        os.environ["PATH"] = ds + os.pathsep + cur


def _host_from_endpoint(endpoint: str) -> str | None:
    """'http://localhost:11434' -> 'localhost:11434' per la env OLLAMA_HOST."""
    host = endpoint.split("://", 1)[-1].rstrip("/")
    return host or None


def start(data_dir: Path, endpoint: str, *, timeout: float = 25.0) -> bool:
    """Avvia `ollama serve` (di sistema o bundled) e attende che risponda su `endpoint`.
    Ritorna True se attivo. Nessun admin: processo utente staccato dalla GUI. False se
    non installato o se non risponde entro `timeout`."""
    base = endpoint.rstrip("/")
    if is_up(base):
        return True
    exe = exe_path(data_dir)
    if not exe:
        return False
    env = dict(os.environ)
    host = _host_from_endpoint(base)
    if host:
        env.setdefault("OLLAMA_HOST", host)  # onora un endpoint custom per il serve avviato da noi
    try:
        kwargs: dict = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = _NO_WIN | _DETACHED
        subprocess.Popen(  # noqa: S603 — exe risolto da PATH/bundle, comando fisso 'serve'
            [exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            **kwargs,
        )
    except OSError:
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.5)
        if is_up(base):
            return True
    return False


def download(data_dir: Path, on_progress=None) -> None:
    """Scarica ed estrae lo ZIP portabile di Ollama in userData/tools/ollama/.
    on_progress(pct 0..1) opzionale. Solleva RuntimeError dove l'auto-installazione non è
    supportata (il chiamante mostra il link al download manuale)."""
    if not can_auto_install():
        from app import runtime_env

        if runtime_env.is_packaged():
            raise RuntimeError(
                "Nella versione Microsoft Store, Ollama va installato manualmente: scaricalo da "
                "https://ollama.com/download (o `winget install Ollama.Ollama`) e riavvia VOKARI — "
                "poi VOKARI lo userà in locale."
            )
        raise RuntimeError(
            "Installazione automatica di Ollama disponibile solo su Windows. "
            "Su questa piattaforma installalo da https://ollama.com/download e riavvia VOKARI."
        )
    d = ollama_dir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    zip_path = d / "_ollama_download.zip"
    req = urllib.request.Request(_WIN_ZIP_URL, headers={"User-Agent": "VOKARI/1.0"})  # noqa: S310 — URL GitHub releases hardcoded
    with urllib.request.urlopen(req, timeout=600) as resp:  # noqa: S310
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(zip_path, "wb") as f:
            while chunk := resp.read(262144):
                f.write(chunk)
                done += len(chunk)
                if on_progress and total:
                    on_progress(done / total)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(d)
    zip_path.unlink(missing_ok=True)
    add_bundled_to_path(data_dir)


def ensure_running(data_dir: Path, endpoint: str, *, install_if_missing: bool = False, on_progress=None) -> bool:
    """Garantisce Ollama attivo su `endpoint`. Se è giù: lo avvia (se installato); se manca e
    `install_if_missing`, scarica+estrae e poi avvia. Ritorna True se attivo a fine procedura."""
    base = endpoint.rstrip("/")
    if is_up(base):
        return True
    if not is_installed(data_dir):
        if not install_if_missing:
            return False
        download(data_dir, on_progress=on_progress)
    return start(data_dir, base)


def stop() -> None:
    """Termina i processi Ollama (serve + app desktop) — best-effort, niente errori se assenti."""
    if sys.platform.startswith("win"):
        for name in ("ollama.exe", "ollama app.exe", "ollama-app.exe"):
            try:
                subprocess.run(  # noqa: S603 — taskkill su nomi eseguibile noti
                    ["taskkill", "/F", "/IM", name],  # noqa: S607
                    capture_output=True,
                    creationflags=_NO_WIN,
                )
            except Exception:  # noqa: S110 — processo non avviato: ok
                pass
    else:
        try:
            subprocess.run(["pkill", "-f", "ollama serve"], capture_output=True)  # noqa: S607
        except Exception:  # noqa: S110
            pass


def uninstall(data_dir: Path) -> None:
    """Rimuove SOLO la copia bundled di Ollama (userData/tools/ollama/). Non tocca
    un'installazione di sistema. Best-effort: i file in uso vengono ignorati."""
    shutil.rmtree(ollama_dir(data_dir), ignore_errors=True)
