"""Log diagnostico VOKARI su file, attivo SOLO se l'env VOKARI_DEBUG è truthy.

Il flusso reale gira in thread di background e in una finestra pywebview: errori,
chiamate js_api e transizioni di status non si vedono. Questo logger li scrive su
`<userData>/data/logs/vokari-debug.log` (JSONL) così il giro è ispezionabile a
posteriori. `enabled()` legge l'env a ogni chiamata: l'harness può attivarlo prima
di importare i moduli applicativi.
"""

import json
import os
import threading
import time
import traceback
from pathlib import Path

from vokari.paths import app_dirs

_LOCK = threading.Lock()


def enabled() -> bool:
    return os.environ.get("VOKARI_DEBUG", "").strip().lower() not in ("", "0", "false", "no", "off")


def log_path() -> Path:
    return app_dirs().data / "logs" / "vokari-debug.log"


def short(obj, limit: int = 240) -> str:
    """Rappresentazione compatta e sicura per il log (tronca i payload lunghi)."""
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        s = repr(obj)
    return s if len(s) <= limit else s[:limit] + f"…(+{len(s) - limit} char)"


def _write(record: dict) -> None:
    try:
        p = log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass  # il logging diagnostico non deve mai rompere il flusso


def log(event: str, **data) -> None:
    if not enabled():
        return
    _write({"ts": round(time.time(), 3), "thread": threading.get_ident(), "event": event, **data})


def log_exc(event: str, exc: BaseException, **data) -> None:
    if not enabled():
        return
    _write(
        {
            "ts": round(time.time(), 3),
            "thread": threading.get_ident(),
            "event": event,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            **data,
        }
    )
