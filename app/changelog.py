"""Changelog "Novità della versione" (Tema 2).

Sorgente: `app/assets/changelog.json` (incluso nella build, NON generato a runtime). Dopo un
aggiornamento dell'app, il frontend mostra un popup con le voci di versione più recenti di
quella vista l'ultima volta (`settings.last_seen_version`). Qui vivono il caricamento del file
e la funzione PURA di selezione/ordinamento — testabile senza I/O.
"""

import json
from pathlib import Path

_ASSETS = Path(__file__).resolve().parent / "assets"


def _parse(v: str) -> tuple[int, ...]:
    """Versione 'X.Y.Z' → tupla di interi confrontabile. I segmenti non numerici (es. 'dev',
    o un suffisso '-rc1') contano 0: una build di sviluppo ('dev'→(0,)) resta "indietro" a
    qualsiasi versione rilasciata, quindi non mostra mai voci di changelog."""
    out: list[int] = []
    for chunk in v.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out) if out else (0,)


def entries_since(entries: list[dict], since: str, current: str) -> list[dict]:
    """Voci con versione > `since` e <= `current`, ordinate dalla più recente.

    - `since` vuoto = nessuna soglia inferiore → tutte le voci fino a `current` (utente che vede
      il changelog per la prima volta dopo l'introduzione della feature).
    - escludendo le voci > `current` una versione futura finita per errore nel file non compare
      prima del suo rilascio.
    """
    cur = _parse(current)
    low = _parse(since) if since else (-1,)  # (-1,) < di qualsiasi versione reale → include tutto
    selected = [e for e in entries if low < _parse(str(e.get("version", "0"))) <= cur]
    return sorted(selected, key=lambda e: _parse(str(e.get("version", "0"))), reverse=True)


def load(path: Path | None = None) -> list[dict]:
    """Legge le voci di changelog dal JSON ({"versions": [...]}). Tollerante: file assente o
    JSON malformato → lista vuota (la feature è additiva, non deve mai rompere l'avvio)."""
    p = path or (_ASSETS / "changelog.json")
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    versions = data.get("versions", []) if isinstance(data, dict) else []
    return versions if isinstance(versions, list) else []
