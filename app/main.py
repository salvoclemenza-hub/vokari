"""Host pywebview: apre una finestra che serve frontend/dist e registra Api."""

import os
import sys
from pathlib import Path

import webview

from app.api import Api


def _find_dist() -> Path:
    """index.html del frontend buildato. In sviluppo: ../frontend/dist/ accanto al repo.
    Installato (wheel pip / Homebrew): app/_webdist/ accanto a questo modulo
    (force-include in pyproject [tool.hatch.build.targets.wheel.force-include]).
    Bundle PyInstaller (.app): i datas finiscono in sys._MEIPASS come dist/ (sotto zip il
    __file__ non è un path reale → la risoluzione relativa non basta)."""
    here = Path(__file__).resolve()
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)  # PyInstaller: dir dei datas raccolti
    if meipass:
        candidates.append(Path(meipass) / "dist" / "index.html")  # bundle .app (PyInstaller)
    candidates += [
        here.parent.parent / "frontend" / "dist" / "index.html",  # sviluppo (repo)
        here.parent / "_webdist" / "index.html",  # installato (wheel/Homebrew)
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # fallback: l'errore è gestito in main()


_ASSETS = Path(__file__).resolve().parent / "assets"


def _icon_path() -> str | None:
    """Icona finestra/taskbar: .ico su Windows, .png altrove. None se mancante."""
    name = "vokari.ico" if sys.platform.startswith("win") else "vokari.png"
    p = _ASSETS / name
    return str(p) if p.exists() else None


def main() -> None:
    import argparse  # import differito: usato solo all'avvio

    parser = argparse.ArgumentParser(prog="vokari-app")
    parser.add_argument("--install-desktop", action="store_true", help="Installa la voce di menu .desktop (Linux)")
    args = parser.parse_args()
    if args.install_desktop:
        from app.desktop_entry import install_desktop_entry

        dest = install_desktop_entry()
        print(f"Voce di menu installata: {dest}")
        return
    dist = _find_dist()
    if not dist.exists():
        sys.exit(f"Frontend non buildato: {dist} mancante.\nEsegui:  cd frontend && pnpm install && pnpm build")
    # Pacchetto distribuibile: rende visibile l'ffmpeg bundlato (no-op in sviluppo → ffmpeg di sistema).
    # Va fatto PRIMA di qualunque uso di ffmpeg (conversione audio) così shutil.which lo trova.
    try:
        from app import ffmpeg_manager

        ffmpeg_manager.add_bundled_to_path()
    except Exception:  # noqa: S110 — best-effort: in sviluppo si usa l'ffmpeg di sistema
        pass
    from app import preflight

    missing = preflight.missing_prereqs()
    if missing:
        sys.exit(preflight.install_hint(missing))
    # Pulizia all'avvio: rimuove le registrazioni temporanee non finalizzate da un crash
    # precedente (dir 'vokari-rec-*' più vecchie di 2h; il filtro età non tocca cattura in corso).
    from vokari.audio import capture as _capture

    _capture.sweep_orphan_tempdirs()

    # Rende l'eventuale Ollama bundled (userData/tools/ollama) visibile a shutil.which/subprocess,
    # così sia il manager sia ollama_provider.ensure_available (pipeline) lo trovano nel PATH.
    try:
        from app import ollama_manager
        from vokari.paths import ensure_dirs

        ollama_manager.add_bundled_to_path(ensure_dirs().data)
    except Exception:  # noqa: S110 — best-effort: l'assenza di Ollama non deve impedire l'avvio
        pass

    api = Api()
    window = webview.create_window(
        "VOKARI",
        url=str(dist),
        js_api=api,
        width=1200,
        height=820,
        min_size=(980, 680),
        background_color="#efe9dd",
    )
    api._window = window
    api.start_resource_monitor()  # indicatore CPU/RAM nella status bar (push periodico)
    api.start_ollama_autostart()  # se brain=ollama e installato ma giù, lo avvia (no 'non in esecuzione')

    # Alla chiusura della finestra silenziamo gli emit verso una webview morente.
    try:
        window.events.closing += lambda: api.shutdown()
    except Exception:  # noqa: S110 — backend pywebview senza events.closing: niente di critico
        pass

    icon = _icon_path()
    try:
        webview.start(icon=icon) if icon else webview.start()
    except TypeError:
        webview.start()  # versione pywebview senza parametro icon

    # Uscita FORZATA: trascrizione (faster-whisper) e anteprima live girano in thread daemon
    # che possono restare bloccati in codice nativo CTranslate2 → senza questo il processo
    # resterebbe vivo dopo la chiusura della finestra ("non si chiude, ancora in elaborazione").
    os._exit(0)


if __name__ == "__main__":
    main()
