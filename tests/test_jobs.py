import os

import pytest
from app.jobs import Job, JobStore


@pytest.fixture
def store(tmp_path):
    return JobStore(jobs_dir=tmp_path / "jobs")


def test_create_get_update_roundtrip(store):
    job = store.create(Job.new("/tmp/a.wav", source="mic", model="small", language="it"))
    assert store.get(job.id).audio_path == "/tmp/a.wav"
    store.update(job.id, status="transcribing", pct=0.5, partial_text="ciao")
    j = store.get(job.id)
    assert j.status == "transcribing" and j.pct == 0.5 and j.partial_text == "ciao"


def test_persistence_survives_new_store_instance(tmp_path):
    d = tmp_path / "jobs"
    s1 = JobStore(jobs_dir=d)
    job = s1.create(Job.new("/tmp/b.wav"))
    s1.update(job.id, status="analyzing")
    s2 = JobStore(jobs_dir=d)
    assert s2.get(job.id).status == "analyzing"


def test_progress_only_updates_are_throttled_on_disk(tmp_path):
    """Update con SOLI pct/partial_text non riscrivono il JSON ad ogni segmento (R6):
    una nuova istanza (che legge da disco) vede solo il primo flush throttato; mentre
    in RAM lo stato è sempre aggiornato."""
    d = tmp_path / "jobs"
    s1 = JobStore(jobs_dir=d)
    job = s1.create(Job.new("/tmp/a.wav"))
    s1.update(job.id, pct=0.1, partial_text="a")  # primo progress → flush
    s1.update(job.id, pct=0.2, partial_text="ab")  # entro 1s → throttato (solo RAM)
    s1.update(job.id, pct=0.3, partial_text="abc")  # entro 1s → throttato
    assert s1.get(job.id).pct == 0.3  # RAM sempre aggiornata
    on_disk = JobStore(jobs_dir=d).get(job.id)
    assert on_disk.pct == 0.1  # disco fermo al primo flush


def test_status_update_always_persists_even_after_progress(tmp_path):
    """Un cambio di status (campo non-progress) forza sempre il flush su disco:
    il resume-da-cache resta esatto."""
    d = tmp_path / "jobs"
    s1 = JobStore(jobs_dir=d)
    job = s1.create(Job.new("/tmp/a.wav"))
    s1.update(job.id, pct=0.5, partial_text="x")
    s1.update(job.id, pct=0.9, partial_text="xy")  # throttato
    s1.update(job.id, status="analyzing", transcript="testo completo")  # forza flush
    on_disk = JobStore(jobs_dir=d).get(job.id)
    assert on_disk.status == "analyzing"
    assert on_disk.transcript == "testo completo"


def test_active_finds_midflight(tmp_path):
    s = JobStore(jobs_dir=tmp_path / "jobs")
    s.create(Job.new("/tmp/done.wav", status="ready"))
    mid = s.create(Job.new("/tmp/mid.wav"))
    s.update(mid.id, status="transcribing")
    active = s.active()
    assert active is not None and active.id == mid.id


def test_active_skips_corrupt_json_file(tmp_path):
    """Un file job a metà scrittura (JSON illeggibile) non deve far esplodere active():
    viene saltato e il job midflight valido viene comunque trovato (C2)."""
    d = tmp_path / "jobs"
    s = JobStore(jobs_dir=d)
    mid = s.create(Job.new("/tmp/mid.wav"))
    s.update(mid.id, status="transcribing")
    # simula un file mid-write: JSON troncato/illeggibile
    (d / "corrupt.json").write_text("{ this is not valid json", encoding="utf-8")
    # nuova istanza → active() rilegge da disco, incluso il file corrotto
    active = JobStore(jobs_dir=d).active()
    assert active is not None and active.id == mid.id


def test_abandon_active_marks_all_midflight_cancelled_including_interview(tmp_path):
    """Alla chiusura PULITA della finestra (A1) TUTTI i job midflight — incluso
    'awaiting_interview' — vengono marcati 'cancelled' così al riavvio NON resuscitano e
    l'app non nag "elaborazione in corso" (feedback 2026-06-15, revisione ADR-025). I
    terminali (ready/cancelled/error) restano invariati."""
    d = tmp_path / "jobs"
    s = JobStore(jobs_dir=d)

    def mk(name, status):
        j = s.create(Job.new(f"/tmp/{name}.wav"))
        s.update(j.id, status=status)
        return j

    transcribing = mk("t", "transcribing")
    queued = mk("q", "queued")
    analyzing = mk("a", "analyzing")
    interview = mk("i", "awaiting_interview")
    ready = mk("r", "ready")

    n = s.abandon_active()
    assert n == 4
    # nuova istanza: lo stato è stato persistito su disco
    s2 = JobStore(jobs_dir=d)
    assert s2.get(transcribing.id).status == "cancelled"
    assert s2.get(queued.id).status == "cancelled"
    assert s2.get(analyzing.id).status == "cancelled"
    assert s2.get(interview.id).status == "cancelled"  # niente nag alla riapertura
    assert s2.get(ready.id).status == "ready"
    # active() non trova più alcun job midflight da riprendere
    assert s2.active() is None


def test_active_returns_most_recent_when_multiple_midflight(tmp_path):
    s = JobStore(jobs_dir=tmp_path / "jobs")
    old = s.create(Job.new("/tmp/old.wav"))
    s.update(old.id, status="transcribing")
    new = s.create(Job.new("/tmp/new.wav"))
    s.update(new.id, status="transcribing")
    # forza mtime: old più vecchio, new più recente
    old_path = tmp_path / "jobs" / f"{old.id}.json"
    new_path = tmp_path / "jobs" / f"{new.id}.json"
    os.utime(old_path, (1000, 1000))
    os.utime(new_path, (2000, 2000))
    # nuova istanza per forzare la lettura da disco
    s2 = JobStore(jobs_dir=tmp_path / "jobs")
    active = s2.active()
    assert active is not None and active.id == new.id
