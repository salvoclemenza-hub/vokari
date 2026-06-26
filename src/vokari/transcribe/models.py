"""Catalogo modelli Whisper locali + stato (scaricato/attivo) + download on-demand.

Lo scaricamento è delegato a faster-whisper (che mappa il nome al repo HuggingFace
e usa la cache hub): non hardcodiamo i repo id, così restiamo robusti tra versioni.
NOTA: faster-whisper accetta 'large-v3-turbo' (alias 'turbo') da v1.0.3+. Se una
versione esponesse solo 'turbo', cambiare il `name` nel CATALOG o aggiungere un alias.
"""

import re
import threading
from dataclasses import dataclass
from pathlib import Path

from faster_whisper.utils import download_model as _download_model

from vokari.paths import app_dirs, ensure_dirs
from vokari.settings import Settings


@dataclass(frozen=True)
class ModelInfo:
    name: str  # nome passato a faster-whisper (es. "large-v3-turbo")
    size_label: str  # dimensione indicativa su disco
    speed: int  # 1..5 (meter velocità, 5 = più veloce)
    quality: int  # 1..5 (meter qualità, 5 = migliore)
    languages: str  # etichetta lingue
    description: str = ""  # breve spiegazione per la UI (quando scegliere questo modello)
    recommended: bool = False


# Ordine = ordine di visualizzazione nella schermata Modelli (handoff §7).
CATALOG: list[ModelInfo] = [
    ModelInfo(
        "tiny",
        "~75 MB",
        5,
        1,
        "IT·EN·+90",
        "Solo anteprima live: ultra-veloce, impreciso. Non adatto per la trascrizione finale.",
    ),
    ModelInfo(
        "base",
        "~145 MB",
        5,
        2,
        "IT·EN·+90",
        "Anteprima live (default): veloce, qualità sufficiente per la bozza in tempo reale.",
    ),
    ModelInfo(
        "small",
        "~0.5 GB",
        5,
        2,
        "IT·EN·+90",
        "Il più veloce e leggero. Qualità di base: buono per prove rapide o PC modesti.",
    ),
    ModelInfo(
        "medium", "~1.5 GB", 3, 3, "IT·EN·+90", "Compromesso tra velocità e accuratezza. Adatto all'uso quotidiano."
    ),
    ModelInfo(
        "large-v3-turbo",
        "~1.6 GB",
        4,
        4,
        "IT·EN·+90",
        "Consigliato: quasi la qualità di large-v3 ma molto più veloce.",
        recommended=True,
    ),
    ModelInfo(
        "large-v3",
        "~3.1 GB",
        2,
        5,
        "IT·EN·+90",
        "Massima accuratezza. Il più lento su CPU: meglio per audio difficili.",
    ),
]


def _cache_dir() -> str:
    # solo il path: nessun side-effect su disco (un controllo read-only non crea dir).
    return str(app_dirs().models)


def is_downloaded(name: str) -> bool:
    """True se il modello è già nella cache locale (nessuna rete, nessun side-effect).

    Cattura solo le eccezioni che indicano 'modello non presente' (huggingface_hub).
    PermissionError e OSError di permessi si propagano: segnalano problemi di disco/cache
    che richiedono attenzione, non l'assenza del modello.
    """
    try:
        _download_model(name, local_files_only=True, cache_dir=_cache_dir())
        return True
    except (OSError, ValueError) as e:
        # huggingface_hub lancia OSError / RepositoryNotFoundError / EntryNotFoundError
        # quando il modello non è in cache. ValueError per nomi non validi.
        # Re-raise se è un problema di permessi:
        if isinstance(e, PermissionError):
            raise
        return False


def download(name: str) -> str:
    """Scarica (se mancante) il modello nella cache di VOKARI. Ritorna il path locale."""
    ensure_dirs()  # crea la dir dei modelli una volta, solo quando serve davvero
    return _download_model(name, local_files_only=False, cache_dir=_cache_dir())


_DL_POLL_S = 1.0  # intervallo di polling per la stima del progresso download


def expected_bytes(name: str) -> int:
    """Byte attesi stimati dal size_label del CATALOG ('~1.6 GB' -> 1_600_000_000). 0 se ignoto."""
    for m in CATALOG:
        if m.name == name:
            mt = re.search(r"([\d.]+)\s*GB", m.size_label)
            if mt:
                return int(float(mt.group(1)) * 1_000_000_000)
    return 0


def _dir_size(path: Path) -> int:
    """Byte totali dei file sotto `path` (best-effort, ignora errori transitori)."""
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def download_with_progress(name: str, on_progress=None) -> str:
    """Scarica `name` (bloccante, via download()) mentre un thread monitor stima il progresso
    dalla crescita della dir modelli e invoca on_progress(bytes_done, bytes_total) ~ogni
    _DL_POLL_S. faster-whisper non espone un callback di progresso reale → la stima evita di
    reimplementarne il download. Rilancia l'eccezione di download() dopo aver fermato il monitor."""
    total = expected_bytes(name)
    models_dir = Path(_cache_dir())
    baseline = _dir_size(models_dir)
    stop = threading.Event()

    def _monitor() -> None:
        while not stop.wait(_DL_POLL_S):
            grown = max(0, _dir_size(models_dir) - baseline)
            if on_progress:
                on_progress(grown, total)

    mon = threading.Thread(target=_monitor, daemon=True)
    if on_progress and total:
        mon.start()
    try:
        return download(name)
    finally:
        stop.set()


def state(name: str, settings: Settings) -> str:
    """'active' (default + scaricato) | 'downloaded' | 'available'."""
    if not is_downloaded(name):
        return "available"
    return "active" if name == settings.whisper_model else "downloaded"
