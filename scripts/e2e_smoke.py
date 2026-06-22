"""Harness end-to-end headless del flusso reale VOKARI (Area A del piano).

Pilota il flusso via `Api` (come fa la GUI) con un audio reale, stampa OGNI
transizione di status + errori + l'output, e scrive il briefing su file.
Serve a testare/diagnosticare l'intero processo senza aprire la finestra.

Uso:
    set VOKARI_DEBUG=1
    python scripts/e2e_smoke.py [audio.m4a]   # default: 183.m4a nel progetto
"""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("VOKARI_DEBUG", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from app import debuglog  # noqa: E402
from app.api import Api  # noqa: E402
from app.jobs import JobStore  # noqa: E402

from vokari import settings as settings_mod  # noqa: E402

_DEFAULT_STOP = ("awaiting_interview", "ready", "error", "cancelled")


def poll(api: Api, jid: str, timeout: float = 900.0, stop_at: tuple = _DEFAULT_STOP) -> dict:
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        j = api.get_job(jid)
        if j:
            key = (j["status"], round(j["pct"], 2))
            if key != last:
                last = key
                err = (j["error"] or "")[:100]
                print(f"  [{time.time() - t0:6.1f}s] status={j['status']:>18}  pct={j['pct']:.2f}  err={err!r}")
            if j["status"] in stop_at:
                return j
        time.sleep(1.0)
    print("  TIMEOUT")
    return api.get_job(jid) or {}


def main() -> int:
    audio = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "183.m4a")
    audio = str(Path(audio).resolve())
    if not Path(audio).exists():
        print(f"AUDIO non trovato: {audio}")
        return 2

    s = settings_mod.load()
    print(f"== settings: brain={s.brain} ollama={s.ollama_model} whisper={s.whisper_model} mode={s.default_mode}")
    print(f"== audio: {audio}")
    print(f"== debug log: {debuglog.log_path()} (enabled={debuglog.enabled()})")

    api = Api(store=JobStore(jobs_dir=tempfile.mkdtemp()))

    print("\n[1] import_file -> pipeline (trascrizione + analisi + domande)")
    r = api.import_file(audio, mode=s.default_mode, title="Smoke 183")
    jid = r.get("jobId")
    print("  jobId:", jid, "| err:", r.get("error"))
    if not jid:
        print("  FALLITO: import_file non ha restituito jobId")
        return 1

    j = poll(api, jid)
    if j.get("status") == "error":
        print("  ERRORE pipeline:", j.get("error"))
        return 1
    print("  trascritto (prime 200):", repr((j.get("transcript") or "")[:200]))
    print("  durata:", j.get("durationS"), "s | domande:", len(j.get("questions", [])))
    for q in j.get("questions", []):
        print("    -", q.get("text", "")[:80])

    print("\n[2] generate briefing (salto tutte le domande)")
    skipped = [q["id"] for q in j.get("questions", [])]
    # C1: generate() ritorna SUBITO (la generazione gira in un thread daemon); come la GUI
    # via evento status, qui facciamo polling fino a ready/error (non awaiting_interview).
    api.generate(jid, {}, skipped)
    jv = poll(api, jid, stop_at=("ready", "error", "cancelled"))
    if jv.get("status") != "ready":
        print("  NON ready:", jv.get("status"), jv.get("error"))
        return 1
    print("  status:", jv["status"], "| briefing_len:", len(jv["briefingMd"]))

    print("\n[3] get_artifacts (output)")
    art = api.get_artifacts(jid)
    print(f"  title={art['title']!r} words={art['wordCount']} model={art['model']} lang={art['language']}")
    out = ROOT / "_smoke_briefing.md"
    out.write_text(art["briefingMd"], encoding="utf-8")
    print("  briefing scritto in:", out)
    print("\n===== BRIEFING (prime 1800) =====")
    print(art["briefingMd"][:1800])
    print("\nOK end-to-end.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
