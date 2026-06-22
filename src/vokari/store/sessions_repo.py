"""Repository delle sessioni completate (la libreria 'second brain').

Persiste su `userData/data/sessions/{id}.json` riusando la dataclass `Session`.
Elenco ordinato per data + ricerca full-text su titolo e trascrizione.
"""

import json
from pathlib import Path

from vokari.paths import ensure_dirs
from vokari.store.session import Session


class SessionsRepo:
    def __init__(self, sessions_dir: str | Path | None = None):
        self._dir = Path(sessions_dir) if sessions_dir else ensure_dirs().data / "sessions"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, sid: str) -> Path:
        return self._dir / f"{sid}.json"

    def save(self, session: Session) -> Session:
        self._path(session.id).write_text(json.dumps(session.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return session

    def get(self, sid: str) -> Session | None:
        p = self._path(sid)
        if not p.exists():
            return None
        return Session.from_dict(json.loads(p.read_text(encoding="utf-8")))

    def delete(self, sid: str) -> bool:
        """Rimuove la sessione dalla libreria. True se esisteva."""
        p = self._path(sid)
        if p.exists():
            p.unlink()
            return True
        return False

    def list_all(self) -> list[Session]:
        items: list[Session] = []
        for p in self._dir.glob("*.json"):
            try:
                items.append(Session.from_dict(json.loads(p.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, OSError):
                continue
        items.sort(key=lambda s: s.created_at, reverse=True)
        return items

    def search(self, query: str) -> list[Session]:
        q = query.strip().lower()
        if not q:
            return self.list_all()
        tokens = q.split()
        out: list[Session] = []
        for s in self.list_all():
            hay = (s.title + " " + (s.transcript or "")).lower()
            if all(tok in hay for tok in tokens):
                out.append(s)
        return out
