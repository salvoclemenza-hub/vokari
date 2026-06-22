"""Job di elaborazione + store con persistenza JSON (resume dopo chiusura finestra).
Un Job mirrora i dati di Session ma vive durante il flusso GUI; persistito sotto
userData/data/jobs/{id}.json cosi che 'riprende da sola' funzioni (resume-da-cache)."""

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path

from vokari.paths import ensure_dirs

_MIDFLIGHT = {"queued", "transcribing", "analyzing", "rendering", "awaiting_interview"}
# Stati abbandonati alla chiusura PULITA della finestra (Api.shutdown → abandon_active):
# TUTTI i midflight, incluso 'awaiting_interview'. Chiudere volontariamente la finestra = "ho
# finito": non deve lasciare una sessione che alla riapertura nag "elaborazione in corso" e
# spinge alla rifinitura LLM — caso tipico delle registrazioni di prova/dettature a metà
# (feedback utente 2026-06-15, revisione di ADR-025). La ripresa-da-CRASH resta garantita:
# dopo un crash Api.shutdown NON viene eseguito, quindi active() ritrova comunque il job
# midflight e offre la pill di ripresa. La distinzione clean-close↔crash è proprio questa.
_ABANDON_ON_SHUTDOWN = _MIDFLIGHT

# Campi ad alta frequenza (avanzamento trascrizione): aggiornati a ogni segmento Whisper.
_PROGRESS_KEYS = {"pct", "partial_text"}
_PROGRESS_FLUSH_S = 1.0  # intervallo minimo tra due scritture su disco per soli progressi


@dataclass
class Job:
    id: str
    audio_path: str
    title: str = "Sessione senza titolo"
    mode: str = "solo"
    context: str = ""
    source: str = "mic"
    model: str = ""
    language: str = "auto"
    status: str = "queued"
    pct: float = 0.0
    partial_text: str = ""
    transcript: str = ""
    duration_s: float = 0.0
    analysis: dict | None = None
    questions: list[dict] = field(default_factory=list)
    markers: list[dict] = field(default_factory=list)
    da_chiarire: list[str] = field(default_factory=list)  # marcatori [DA CHIARIRE] (export Obsidian completo)
    briefing_md: str = ""
    briefing_path: str = ""
    recap_md: str = ""
    obsidian_note: str = ""
    error: str = ""
    created_at: str = ""

    @classmethod
    def new(cls, audio_path: str, **kw) -> "Job":
        kw.setdefault("created_at", datetime.now(UTC).isoformat())
        return cls(id=uuid.uuid4().hex, audio_path=audio_path, **kw)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


class JobStore:
    def __init__(self, jobs_dir=None):
        self._dir = Path(jobs_dir) if jobs_dir else ensure_dirs().data / "jobs"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._last_flush: dict[str, float] = {}  # ultimo flush su disco per job (throttle progressi)

    def _path(self, jid: str) -> Path:
        return self._dir / f"{jid}.json"

    def _persist(self, job: Job) -> None:
        self._path(job.id).write_text(json.dumps(job.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def create(self, job: Job) -> Job:
        with self._lock:
            self._jobs[job.id] = job
            self._persist(job)
        return job

    def get(self, jid: str) -> Job | None:
        with self._lock:
            if jid in self._jobs:
                return self._jobs[jid]
            p = self._path(jid)
            if p.exists():
                job = Job.from_dict(json.loads(p.read_text(encoding="utf-8")))
                self._jobs[jid] = job
                return job
        return None

    def update(self, jid: str, **changes) -> Job:
        with self._lock:
            job = self._jobs.get(jid)
            if job is None:
                p = self._path(jid)
                if not p.exists():
                    raise KeyError(jid)
                job = Job.from_dict(json.loads(p.read_text(encoding="utf-8")))
                self._jobs[jid] = job
            for k, v in changes.items():
                setattr(job, k, v)
            # Throttle: se l'update tocca SOLO pct/partial_text (centinaia di volte durante
            # la trascrizione di un file lungo → I/O O(n²) sul JSON crescente), scrivi su
            # disco al più ogni _PROGRESS_FLUSH_S. Ogni altro campo (status, transcript, …)
            # persiste sempre: il resume-da-cache resta esatto, il partial_text si ri-deriva
            # comunque dalla cache di trascrizione al resume.
            only_progress = bool(changes) and set(changes).issubset(_PROGRESS_KEYS)
            now = time.monotonic()
            if only_progress and now - self._last_flush.get(jid, 0.0) < _PROGRESS_FLUSH_S:
                return job
            self._last_flush[jid] = now
            self._persist(job)
        return job

    def delete(self, jid: str) -> bool:
        """Rimuove il job dalla cache e da disco (usato quando si elimina la sessione)."""
        with self._lock:
            self._jobs.pop(jid, None)
            self._last_flush.pop(jid, None)
            p = self._path(jid)
            if p.exists():
                p.unlink()
                return True
        return False

    def active(self) -> Job | None:
        with self._lock:
            seen: dict[str, Job] = dict(self._jobs)
        for p in self._dir.glob("*.json"):
            jid = p.stem
            if jid not in seen:
                try:
                    seen[jid] = Job.from_dict(json.loads(p.read_text(encoding="utf-8")))
                except (json.JSONDecodeError, OSError):
                    # File a metà scrittura (write_text non atomico su Windows) o illeggibile:
                    # saltalo invece di propagare JSONDecodeError al resume (C2).
                    continue
        candidates = []
        for job in seen.values():
            if job.status in _MIDFLIGHT:
                try:
                    mtime = self._path(job.id).stat().st_mtime
                except OSError:
                    mtime = 0.0
                candidates.append((mtime, job))
        if not candidates:
            return None
        candidates.sort(key=lambda t: t[0], reverse=True)
        return candidates[0][1]

    def abandon_active(self) -> int:
        """Marca 'cancelled' tutti i job midflight (vedi _ABANDON_ON_SHUTDOWN, incluso
        awaiting_interview), leggendo anche quelli persistiti su disco non ancora in cache.
        Chiamato da Api.shutdown(): senza, al riavvio active() li ritroverebbe e l'app
        nag "elaborazione in corso" spingendo alla rifinitura (A1 + feedback 2026-06-15).
        Ritorna quanti job sono stati abbandonati."""
        with self._lock:
            # popola la cache con i job persistiti su disco (es. avviati prima del riavvio)
            for p in self._dir.glob("*.json"):
                jid = p.stem
                if jid not in self._jobs:
                    try:
                        self._jobs[jid] = Job.from_dict(json.loads(p.read_text(encoding="utf-8")))
                    except (json.JSONDecodeError, OSError):
                        continue
            n = 0
            for job in self._jobs.values():
                if job.status in _ABANDON_ON_SHUTDOWN:
                    job.status = "cancelled"
                    self._persist(job)
                    n += 1
        return n
