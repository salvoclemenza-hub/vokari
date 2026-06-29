"""Classe Api esposta al frontend via window.pywebview.api.
M6: recording + processing + interview + artifacts. I metodi sono snake_case;
le chiavi dei dict di ritorno sono camelCase (contratto JS, ADR-009).
M7-E/G: settings round-trip + models AI cablati.
M7-F/H: sessioni + export PDF/Obsidian."""

import functools
import json
import os
import re
import sys
import threading
import webbrowser
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

from app import changelog as changelog_mod
from app import debuglog
from app import pipeline as pipeline_mod
from app.jobs import Job, JobStore
from vokari import i18n
from vokari import settings as settings_mod
from vokari.analyze.schema import Analysis
from vokari.audio import capture
from vokari.paths import ensure_dirs
from vokari.render import obsidian as obsidian_mod
from vokari.render import pdf as pdf_mod
from vokari.store.session import Session
from vokari.store.sessions_repo import SessionsRepo
from vokari.transcribe import models as models_mod


def _vokari_version() -> str:
    try:
        return _pkg_version("vokari")
    except PackageNotFoundError:
        return "0.1.2"


_GITHUB_REPO = "salvoclemenza-hub/vokari"
_stars_cache: dict[str, int | None] = {"value": None}


def _github_stars() -> int:
    """Conteggio reale delle stelle del repo (cache di processo, timeout breve).
    Repo privato / offline → 0 (la titlebar nasconde la stella finché è 0): il numero
    comparirà da sé quando il repo diventerà pubblico e riceverà stelle."""
    if _stars_cache["value"] is not None:
        return _stars_cache["value"]
    stars = 0
    try:
        import httpx

        r = httpx.get(
            f"https://api.github.com/repos/{_GITHUB_REPO}",
            timeout=2.5,
            headers={"Accept": "application/vnd.github+json"},
        )
        if r.status_code == 200:
            stars = int(r.json().get("stargazers_count", 0) or 0)
    except Exception:
        stars = 0
    _stars_cache["value"] = stars
    return stars


def _file_dialog(kind: str):
    """Costante per Window.create_file_dialog, tollerante alla versione di pywebview.
    pywebview 5.x espone l'enum `FileDialog.{OPEN,FOLDER,SAVE}`; le versioni precedenti
    usavano le costanti modulo `{OPEN,FOLDER,SAVE}_DIALOG` (ora deprecate → warning a runtime).
    `kind` ∈ {"OPEN", "FOLDER", "SAVE"}."""
    import webview

    fd = getattr(webview, "FileDialog", None)
    if fd is not None:
        return getattr(fd, kind)
    return getattr(webview, f"{kind}_DIALOG")


# Modelli Ollama raccomandati per il dominio italiano.
# Oltre a name/sizeLabel/description ("per quale idea"), ogni voce porta i metadati
# "scheda modello" (stile Lemonade) per scegliere a colpo d'occhio: speed/quality come
# meter 0..3 (indicativi su CPU), params, context, tags e detailUrl (pagina dettagli del
# modello). Consumati da Models.tsx → sezione "Modelli locali · Ollama".
_OLLAMA_CATALOG = [
    {
        "name": "qwen2.5:7b",
        "sizeLabel": "~4.7 GB",
        "description": "Miglior compromesso: ottimo italiano, JSON affidabile, veloce su CPU — il default.",
        "speed": 3,
        "quality": 2,
        "params": "7B",
        "context": "128K",
        "tags": ["italiano", "json", "veloce"],
        "detailUrl": "https://ollama.com/library/qwen2.5",
    },
    {
        "name": "qwen3:4b-instruct",
        "sizeLabel": "~2.6 GB",
        "description": "Nuova gen Qwen3: veloce, leggero, ottimo italiano; per dispositivi con poca RAM.",
        "speed": 3,
        "quality": 2,
        "params": "4B",
        "context": "128K",
        "tags": ["italiano", "leggero", "veloce"],
        "detailUrl": "https://ollama.com/library/qwen3",
    },
    {
        "name": "gemma3:4b-instruct",
        "sizeLabel": "~2.5 GB",
        "description": "Gemma3 leggero: reasoning pulito, istruzioni affidabili, multilingue.",
        "speed": 3,
        "quality": 2,
        "params": "4B",
        "context": "8K",
        "tags": ["multilingue", "reasoning", "leggero"],
        "detailUrl": "https://ollama.com/library/gemma3",
    },
    {
        "name": "llama3.1:8b",
        "sizeLabel": "~4.7 GB",
        "description": "Modello generale solido con buon italiano: alternativa validata ai Qwen.",
        "speed": 2,
        "quality": 2,
        "params": "8B",
        "context": "128K",
        "tags": ["italiano", "multilingue"],
        "detailUrl": "https://ollama.com/library/llama3.1",
    },
    {
        "name": "qwen2.5:14b",
        "sizeLabel": "~9 GB",
        "description": "Massima qualità e ragionamento; richiede >16 GB di RAM.",
        "speed": 1,
        "quality": 3,
        "params": "14B",
        "context": "128K",
        "tags": ["italiano", "reasoning"],
        "detailUrl": "https://ollama.com/library/qwen2.5",
    },
]


def _derive_params(name: str) -> str:
    """Ricava i parametri (es. '7B') dal tag del nome modello ('qwen2.5:7b'→'7B',
    'deepseek-coder:6.7b'→'6.7B'). Vuoto se il tag non porta una taglia ('llama3:latest')."""
    tag = name.split(":")[-1] if ":" in name else name
    m = re.search(r"(\d+(?:\.\d+)?)\s*b\b", tag, re.IGNORECASE)
    return f"{m.group(1)}B" if m else ""


def _min_ram_gb(size_label: str) -> float:
    """MOD2: stima la RAM minima consigliata per eseguire un modello dal suo size_label (la
    dimensione quantizzata su disco è la base reale): pesi + cache di contesto + overhead di
    runtime ≈ dimensione x 1.3. 0 se la dimensione è ignota ('?') → nessun avviso/filtro
    (non inventiamo un requisito). Indicativo, è una guida non un vincolo."""
    m = re.search(r"([\d.]+)\s*GB", size_label)
    return round(float(m.group(1)) * 1.3, 1) if m else 0.0


def _is_embedding_model(name: str) -> bool:
    """I modelli di embedding (nomic-embed-text, *-embed-*) non generano briefing: vanno
    esclusi dall'elenco dei "cervelli" Ollama (altrimenti producono output inutilizzabile)."""
    return "embed" in name.split(":")[0].lower()


def _match_curated(name: str) -> dict | None:
    """Trova la voce di catalogo per un modello installato. Match esatto, poi tollerante:
    stessa famiglia base + stessa taglia (così 'qwen2.5:7b-instruct-q4_K_M' eredita i
    metadati di 'qwen2.5:7b'). Le taglie diverse (7b vs 14b) restano distinte."""
    for c in _OLLAMA_CATALOG:
        if c["name"] == name:
            return c
    base = name.split(":")[0].lower()
    size = _derive_params(name)
    if not size:
        return None
    for c in _OLLAMA_CATALOG:
        if c["name"].split(":")[0].lower() == base and _derive_params(c["name"]) == size:
            return c
    return None


def _ollama_entry(
    name: str, *, size_label: str, curated: dict | None, installed: bool, active: bool, lang: str = "it"
) -> dict:
    """Costruisce una voce OllamaModelEntry (== interface in bridge.ts).

    I metadati "scheda modello" (speed/quality/context/tags/detailUrl) vengono dal catalogo
    curato. Per un modello installato fuori catalogo: speed/quality/tags restano neutri (non
    inventiamo metriche), ma deriviamo `params` dal nome e mostriamo una descrizione neutra
    così la card resta coerente con le altre invece di apparire "rotta" (fix Phase C).
    `lang` (app_language) localizza descrizione e tag (card "Modelli AI")."""
    detail = (curated or {}).get("detailUrl") or f"https://ollama.com/library/{name.split(':')[0]}"
    # description: dal catalogo i18n per nome (fallback al testo IT del catalogo); fuori-catalogo → off_desc.
    if curated:
        description = i18n.model_desc(name, lang) or curated.get("description", "")
    else:
        description = i18n.t("models.off_desc", lang) if installed else ""
    return {
        "name": name,
        "sizeLabel": size_label,
        "description": description,
        "speed": curated.get("speed", 0) if curated else 0,
        "quality": curated.get("quality", 0) if curated else 0,
        "params": curated.get("params", "") if curated else _derive_params(name),
        "context": curated.get("context", "") if curated else "",
        "tags": i18n.model_tags(curated.get("tags", []), lang) if curated else [],
        "detailUrl": detail,
        "minRamGb": _min_ram_gb(size_label),  # MOD2: RAM minima stimata (0 = ignota → nessun avviso)
        "isInstalled": installed,
        "isActive": active,
        "recommended": curated is not None,
    }


def _traced(method):
    """Logga ogni chiamata js_api (e l'eventuale eccezione) se VOKARI_DEBUG è attivo.
    Redige gli argomenti dei metodi che maneggiano chiavi."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        safe = "<redacted>" if "key" in method.__name__ else debuglog.short(args)
        debuglog.log("api_call", method=method.__name__, args=safe)
        try:
            result = method(self, *args, **kwargs)
            debuglog.log("api_return", method=method.__name__, result=debuglog.short(result))
            return result
        except Exception as e:
            debuglog.log_exc("api_error", e, method=method.__name__)
            raise

    return wrapper


def _job_view(job: Job) -> dict:
    """Proiezione camelCase del Job per il JS."""
    return {
        "jobId": job.id,
        "title": job.title,
        "status": job.status,
        "pct": job.pct,
        "source": job.source,
        "mode": job.mode,
        "model": job.model,
        "language": job.language,
        "partialText": job.partial_text,
        "transcript": job.transcript,
        "durationS": job.duration_s,
        "questions": job.questions,
        "markers": job.markers,
        "briefingMd": job.briefing_md,
        "draftBriefing": job.draft_briefing,
        "briefingPath": job.briefing_path,
        "error": job.error,
    }


def _session_list_item(s) -> dict:
    """Proiezione camelCase di una Session per la lista sessioni (F)."""
    arts = s.artifacts or {}
    return {
        "id": s.id,
        "title": s.title,
        "createdAt": s.created_at,
        "mode": s.mode,
        "model": s.model,
        "durationMs": s.duration_ms,
        "hasBriefing": bool(arts.get("briefing_md")),
        "hasRecap": bool(arts.get("recap_md")),
        "hasObsidian": bool(arts.get("obsidian_note")),
        # S1: domande rimaste "da chiarire" nel briefing (marcatore [DA CHIARIRE: ...]) → chip
        # ambra in lista per vedere a colpo d'occhio i briefing incompleti. Nessun I/O extra.
        "clarCount": (arts.get("briefing_md", "") or "").count("[DA CHIARIRE"),
        # S2: l'audio è disponibile solo se il file locale esiste ancora (per gli import il path
        # punta al file originale dell'utente, che può essere spostato/cancellato) → il bottone
        # "Riproduci" si mostra solo quando c'è davvero qualcosa da aprire.
        "hasAudio": bool(s.audio_path) and Path(s.audio_path).exists(),
    }


def _question_view(q: dict) -> dict:
    """Proiezione camelCase di una Question (dict model_dump snake_case) per il frontend Interview.
    Mappa from_audio→fromAudio (I2) ed espone why (I1). Tollerante: campi assenti → default."""
    return {
        "id": q.get("id", ""),
        "text": q.get("text", ""),
        "priority": q.get("priority", "medium"),
        "suggestions": q.get("suggestions") or [],
        "why": q.get("why", "") or "",
        "fromAudio": bool(q.get("from_audio", False)),
    }


def _slug(text: str) -> str:
    keep = "".join(c if c.isalnum() or c in " -_" else "" for c in text).strip()
    return ("-".join(keep.split()) or "sessione").lower()[:60]


class Api:
    def __init__(self, store: JobStore | None = None, sessions: SessionsRepo | None = None):
        self._store = store or JobStore()
        self._sessions = sessions or SessionsRepo()
        self._rec: capture.Recorder | None = None
        self._live = None  # LiveTranscriber attivo durante la registrazione (se live_preview)
        self._window = None  # impostato da app/main.py dopo create_window
        self._generate_impl = pipeline_mod.generate_briefing
        self._res_thread: threading.Thread | None = None
        self._res_stop = threading.Event()  # set da shutdown() per fermare il monitor risorse
        self._ollama_pull_cancel: set[str] = set()  # MOD1: nomi di pull Ollama da interrompere

    # --- ponte eventi -------------------------------------------------
    def _emit(self, event: str, payload: dict) -> None:
        debuglog.log("emit", name=event, payload=debuglog.short(payload))
        if self._window is None:
            return
        try:
            self._window.evaluate_js(f"window.__vokari_emit({json.dumps(event)}, {json.dumps(payload)})")
        except Exception as e:
            debuglog.log_exc("emit_error", e, name=event)

    def _lang(self) -> str:
        """Lingua dell'app (app_language) per localizzare i messaggi restituiti alla UI."""
        return i18n.normalize_lang(settings_mod.load().app_language)

    # --- chrome (M5) --------------------------------------------------
    def get_app_info(self) -> dict:
        return {"version": _vokari_version(), "license": "MIT", "githubStars": _github_stars()}

    @_traced
    def get_changelog(self, since: str = "") -> dict:
        """Novità della versione (Tema 2): voci di versione > `since` e <= versione corrente,
        dalla più recente. `since` = settings.last_seen_version (vuoto la prima volta). Le chiavi
        delle voci sono già camelCase (vengono dal JSON versionato `app/assets/changelog.json`).
        Il frontend mostra il popup solo se `entries` è non vuoto (gate via versione vista)."""
        current = _vokari_version()
        entries = changelog_mod.entries_since(changelog_mod.load(), since, current)
        return {"currentVersion": current, "entries": entries}

    def system_specs(self) -> dict:
        """MOD2: specifiche hardware per i suggerimenti di compatibilità modelli.
        ramTotalGb = RAM fisica totale (GiB). 0 se psutil non è disponibile → la UI non mostra
        avvisi né il filtro "Compatibili" (non inventiamo un dato che non abbiamo)."""
        try:
            import psutil

            return {"ramTotalGb": round(psutil.virtual_memory().total / (1024**3), 1)}
        except Exception:
            return {"ramTotalGb": 0.0}

    def flash_taskbar(self) -> dict:
        """Lampeggia l'icona della finestra nella taskbar (Windows) per richiamare
        l'utente quando la finestra è in background — il flusso dura minuti. No-op fuori
        Windows o se l'handle nativo non è disponibile: la notifica HTML5 + beep restano
        il richiamo principale, questo è additivo e best-effort."""
        if self._window is None or not sys.platform.startswith("win"):
            return {"ok": False}
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(self._window.native.Handle)  # pywebview WebView2 → WinForms Form

            class _FLASHWINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.UINT),
                    ("hwnd", wintypes.HWND),
                    ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT),
                    ("dwTimeout", wintypes.DWORD),
                ]

            flash_all, flash_timernofg = 0x3, 0xC  # FLASHW_ALL | FLASHW_TIMERNOFG (finché non in foreground)
            info = _FLASHWINFO(ctypes.sizeof(_FLASHWINFO), hwnd, flash_all | flash_timernofg, 5, 0)
            ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
            return {"ok": True}
        except Exception as e:
            debuglog.log_exc("flash_taskbar_error", e)
            return {"ok": False}

    def open_url(self, url: str) -> dict:
        """Apre un URL nel browser di sistema. In pywebview un <a href> esterno dirotterebbe
        la finestra → il frontend chiama questo metodo per i link (es. repository GitHub)."""
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return {"ok": False, "error": i18n.t("api.invalid_url", self._lang())}
        try:
            webbrowser.open(url)
            return {"ok": True}
        except Exception as e:
            debuglog.log_exc("open_url_error", e)
            return {"ok": False, "error": str(e)}

    # --- monitor risorse (status bar) ---------------------------------
    def start_resource_monitor(self, interval: float = 1.5) -> None:
        """Avvia un thread daemon che emette periodicamente l'uso risorse dello **stack VOKARI**
        (evento `resource_usage` {cpu: % della macchina 0..100, ramMb: RAM totale in MB}) per la
        status bar. Aggrega il processo VOKARI + figli (Whisper gira in-process, ffmpeg) **e i
        processi Ollama** (serve/app/runner del modello: girano staccati, altrimenti il carico
        dell'analisi — modello in RAM + inferenza — resterebbe invisibile). No-op se psutil manca
        o se già avviato. Best-effort: un errore di lettura/emit non deve mai fermare nulla."""
        try:
            import psutil
        except ImportError:
            debuglog.log("resource_monitor", status="psutil_missing")
            return
        if self._res_thread is not None and self._res_thread.is_alive():
            return
        # Ri-armabile dopo uno shutdown precedente (che ha fatto _res_stop.set()): senza
        # ricreare l'Event il nuovo loop uscirebbe subito. Stato consistente per test/embedding.
        self._res_stop = threading.Event()

        def _read_temp() -> float | None:
            """Temperatura CPU in °C.
            Cascade: psutil (Linux/macOS) → ACPI WMI → OpenHardwareMonitor WMI →
            LibreHardwareMonitor WMI (Windows). None se nessun metodo funziona."""
            # Linux / macOS
            if hasattr(psutil, "sensors_temperatures"):
                try:
                    temps = psutil.sensors_temperatures()
                    for key in ("coretemp", "k10temp", "cpu_thermal", "cpu-thermal", "acpitz"):
                        entries = temps.get(key, [])
                        if entries:
                            return round(max(e.current for e in entries), 1)
                    for entries in temps.values():
                        if entries:
                            return round(max(e.current for e in entries), 1)
                except Exception:  # noqa: S110 — psutil fallback, silenzioso è corretto
                    pass
                return None
            # Windows: cascade ACPI → OHM → LHM in un unico subprocess PowerShell.
            # ACPI richiede admin su molti sistemi; OHM/LHM funzionano senza admin se
            # l'applicazione è in esecuzione (espongono i sensori via WMI).
            # Usare nomi completi dei parametri (gli alias -NS/-CN/-EA non sono universali).
            # Fallback: sensori Temperature anche senza 'Name -match CPU' (sistemi senza
            # nome sensore standard → prende il massimo tra tutti i sensori temperatura).
            _PS = (
                "$t=(Get-CimInstance -Namespace root/WMI -ClassName MSAcpi_ThermalZoneTemperature"
                " -ErrorAction SilentlyContinue).CurrentTemperature;"
                "if($t){[math]::Round((($t|Measure-Object -Maximum).Maximum/10.0)-273.15,1);exit};"
                "foreach($ns in 'root/OpenHardwareMonitor','root/LibreHardwareMonitor'){"
                "  $s=Get-CimInstance -Namespace $ns -ClassName Sensor -ErrorAction SilentlyContinue"
                "  |Where-Object{$_.SensorType -eq 'Temperature' -and $_.Name -match 'CPU'};"
                "  if($s){[math]::Round(($s|Measure-Object -Property Value -Maximum).Maximum,1);exit}"
                "  $sAll=Get-CimInstance -Namespace $ns -ClassName Sensor -ErrorAction SilentlyContinue"
                "  |Where-Object{$_.SensorType -eq 'Temperature'};"
                "  if($sAll){[math]::Round(($sAll|Measure-Object -Property Value -Maximum).Maximum,1);exit}"
                "}"
            )
            try:
                import subprocess

                _NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                r = subprocess.run(  # noqa: S603
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS],  # noqa: S607
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=_NO_WIN,
                )
                raw = r.stdout.strip()
                if raw:
                    return float(raw)
            except Exception:  # noqa: S110 — PowerShell fallback temperatura, silenzioso ok
                pass
            return None

        _TEMP_FIRST = 2  # primo aggiornamento temperatura dopo N tick (risposta rapida)
        _TEMP_INTERVAL = 5  # aggiornamenti successivi ogni N tick (~7.5 s in regime)
        # Nomi dei processi Ollama: `ollama serve` è avviato STACCATO (DETACHED) e gira come
        # processo separato, NON come figlio di VOKARI → va incluso per nome, altrimenti il
        # grosso del carico durante l'analisi (modello in RAM + inferenza) resta invisibile.
        _OLLAMA_NAMES = {"ollama.exe", "ollama", "ollama app.exe", "ollama-app.exe", "ollama_llama_server.exe"}

        def _relevant_procs() -> dict:
            """PID rilevanti per lo stack VOKARI: processo VOKARI + figli (Whisper gira in-process,
            ffmpeg ecc. sono figli) + processi Ollama (serve/app/runner) + loro figli. Dedup per PID."""
            seen: dict = {}
            roots = []
            try:
                roots.append(psutil.Process())
            except psutil.Error:
                pass
            try:
                for p in psutil.process_iter(["name"]):
                    if (p.info.get("name") or "").lower() in _OLLAMA_NAMES:
                        roots.append(p)
            except psutil.Error:
                pass
            for r in roots:
                try:
                    seen[r.pid] = r
                    for c in r.children(recursive=True):
                        seen.setdefault(c.pid, c)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return seen

        def _loop() -> None:
            cpu_count = psutil.cpu_count() or 1
            tracked: dict = {}  # pid -> Process riusato tra i tick (cpu_percent dà il delta dall'ultima lettura)
            try:
                me = psutil.Process()
                me.cpu_percent(interval=None)  # priming: la prima lettura sarebbe 0.0
                tracked[me.pid] = me
            except psutil.Error:
                pass
            tick = 0
            temp_c: float | None = None
            while not self._res_stop.wait(interval):
                try:
                    relevant = _relevant_procs()
                    cpu_raw = 0.0  # somma dei cpu_percent per-processo (può superare 100% su più core)
                    ram_mb = 0.0
                    next_tracked: dict = {}
                    for pid, p in relevant.items():
                        obj = tracked.get(pid, p)  # riusa l'oggetto del tick precedente per il delta CPU corretto
                        try:
                            cpu_raw += obj.cpu_percent(interval=None)
                            ram_mb += obj.memory_info().rss / (1024 * 1024)
                            next_tracked[pid] = obj
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    tracked = next_tracked
                    cpu_pct = min(100.0, cpu_raw / cpu_count)  # normalizzato a % della macchina (somma core / n core)
                    payload: dict = {"cpu": round(cpu_pct, 1), "ramMb": round(ram_mb)}
                    if temp_c is not None:
                        payload["tempC"] = temp_c
                    self._emit("resource_usage", payload)
                    # Temperatura dopo l'emit: non ritarda il primo tick;
                    # su Windows il subprocess PowerShell può essere lento.
                    tick += 1
                    threshold = _TEMP_FIRST if temp_c is None else _TEMP_INTERVAL
                    if tick % threshold == 0:
                        temp_c = _read_temp()
                except Exception as e:
                    debuglog.log_exc("resource_monitor_error", e)

        self._res_thread = threading.Thread(target=_loop, daemon=True)
        self._res_thread.start()

    def shutdown(self) -> None:
        """Chiusura finestra: ferma il lavoro in background (best-effort, NON blocca).
        I worker (trascrizione faster-whisper, anteprima live) girano in thread daemon che
        possono restare appesi in codice nativo CTranslate2 → l'interprete non termina pulito
        e il processo resta vivo "ancora in elaborazione". Azzerare `_window` rende no-op ogni
        `_emit` (monitor/live/pipeline silenziati); `main.py` forza l'uscita del processo dopo
        `webview.start()`. Non joina i thread per non ritardare la chiusura della finestra."""
        self._window = None
        self._res_stop.set()
        # A1: abbandona TUTTI i job midflight (incluso awaiting_interview) così al riavvio
        # NON resuscitano e l'app non nag "elaborazione in corso" (feedback 2026-06-15).
        # La ripresa-da-crash resta: dopo un crash questo non gira e active() li ritrova.
        try:
            self._store.abandon_active()
        except Exception as e:
            debuglog.log_exc("shutdown_abandon_error", e)

    # --- impostazioni (E) ---------------------------------------------
    @_traced
    def get_settings(self) -> dict:
        """Ritorna le impostazioni correnti in camelCase. La chiave API NON viene mai restituita in chiaro."""
        s = settings_mod.load()
        return {
            "brain": s.brain,
            "ollamaEndpoint": s.ollama_endpoint,
            "ollamaModel": s.ollama_model,
            "whisperModel": s.whisper_model,
            "claudeModel": s.claude_model,
            "briefingDir": s.briefing_dir,
            "obsidianVault": s.obsidian_vault,
            "defaultMode": s.default_mode,
            "transcriptionLanguage": s.transcription_language,
            "livePreview": s.live_preview,
            "liveModel": s.live_model,
            "onboarded": s.onboarded,
            "lastSeenVersion": s.last_seen_version,
            "appLanguage": s.app_language,
            "userContext": s.user_context,
            "hasApiKey": bool(settings_mod.get_api_key()),
        }

    @_traced
    def save_settings(self, patch: dict) -> dict:
        """Accetta un dict camelCase parziale, fa merge su settings correnti, salva e ritorna get_settings()."""
        _CAMEL_TO_SNAKE = {
            "brain": "brain",
            "ollamaEndpoint": "ollama_endpoint",
            "ollamaModel": "ollama_model",
            "whisperModel": "whisper_model",
            "claudeModel": "claude_model",
            "briefingDir": "briefing_dir",
            "obsidianVault": "obsidian_vault",
            "defaultMode": "default_mode",
            "transcriptionLanguage": "transcription_language",
            "livePreview": "live_preview",
            "liveModel": "live_model",
            "onboarded": "onboarded",
            "lastSeenVersion": "last_seen_version",
            "appLanguage": "app_language",
            "userContext": "user_context",
        }
        s = settings_mod.load()
        for camel, snake in _CAMEL_TO_SNAKE.items():
            if camel in patch:
                setattr(s, snake, patch[camel])
        settings_mod.save(s)
        return self.get_settings()

    @_traced
    def set_api_key(self, key: str) -> dict:  # nome contiene "key" → log redatto da _traced
        """Salva la chiave API nel keyring OS (mai nel settings.json)."""
        settings_mod.set_api_key(key)
        return {"ok": True, "hasApiKey": True}

    @_traced
    def delete_api_key(self) -> dict:  # nome contiene "key" → log redatto da _traced
        """SET2: rimuove la chiave API dal keyring. La card Impostazioni torna a 'non impostata'."""
        settings_mod.delete_api_key()
        return {"ok": True, "hasApiKey": False}

    @_traced
    def verify_api_key(self) -> dict:  # nome contiene "key" → log redatto da _traced
        """SET1: verifica che la chiave Claude salvata sia valida e Claude raggiungibile con una
        chiamata minimale (max_tokens=1). Ritorna {ok: chiave valida, reachable: server raggiunto,
        error}. Sync con timeout corto (un ping è breve). La chiave NON viene mai loggata; l'errore
        restituito è generico. Speculare al pre-flight Ollama: scopre subito una chiave errata
        invece che a fine trascrizione."""
        s = settings_mod.load()
        lang = i18n.normalize_lang(s.app_language)
        key = settings_mod.get_api_key()
        if not key:
            return {"ok": False, "reachable": False, "error": i18n.t("api.no_api_key", lang)}
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=key, timeout=15.0)
            client.messages.create(model=s.claude_model, max_tokens=1, messages=[{"role": "user", "content": "ping"}])
            return {"ok": True, "reachable": True, "error": ""}
        except anthropic.AuthenticationError:
            return {"ok": False, "reachable": True, "error": i18n.t("api.key_invalid", lang)}
        except anthropic.APIConnectionError:
            return {"ok": False, "reachable": False, "error": i18n.t("api.claude_unreachable", lang)}
        except Exception as e:
            debuglog.log_exc("verify_api_key_error", e)
            return {"ok": False, "reachable": False, "error": i18n.t("api.verify_failed", lang)}

    @_traced
    def browse_folder(self) -> dict:
        """Apre il selettore cartella nativo. Ritorna {"path": ""} se annullato o fuori pywebview."""
        if self._window is None:
            return {"path": ""}
        res = self._window.create_file_dialog(_file_dialog("FOLDER"))
        return {"path": res[0] if res else ""}

    # --- modelli AI (G) -----------------------------------------------
    @_traced
    def list_models(self) -> list:
        """Lista CATALOG con state reale (active/downloaded/available)."""
        s = settings_mod.load()
        result = []
        for m in models_mod.CATALOG:
            result.append(
                {
                    "name": m.name,
                    "sizeLabel": m.size_label,
                    "speed": m.speed,
                    "quality": m.quality,
                    "languages": m.languages,
                    "description": m.description,
                    "recommended": m.recommended,
                    "state": models_mod.state(m.name, s),
                }
            )
        return result

    @_traced
    def download_model(self, name: str) -> dict:
        """Scarica un modello Whisper in background thread. Emette eventi model_download via push
        (start → progress* → done|error). Ritorna subito per non bloccare il thread pywebview.

        Il progresso è STIMATO dalla crescita della dir modelli (faster-whisper non espone un
        callback reale) — vedi models.download_with_progress."""
        expected = models_mod.expected_bytes(name)

        def _do_download():
            self._emit("model_download", {"name": name, "status": "start", "totalBytes": expected})
            try:
                models_mod.download_with_progress(
                    name,
                    on_progress=lambda done, total: self._emit(
                        "model_download",
                        {
                            "name": name,
                            "status": "progress",
                            "pct": round(min(0.99, done / total), 3) if total else 0.0,
                            "bytesDone": done,
                            "bytesTotal": total,
                        },
                    ),
                )
                self._emit("model_download", {"name": name, "status": "done"})
            except Exception as e:
                debuglog.log_exc("model_download_error", e, name=name)
                self._emit("model_download", {"name": name, "status": "error", "error": str(e)})

        threading.Thread(target=_do_download, daemon=True).start()
        return {"ok": True}  # ritorna subito; il vero stato arriva via evento

    @_traced
    def set_active_model(self, name: str) -> dict:
        """Imposta whisper_model nelle impostazioni. Ritorna get_settings()."""
        return self.save_settings({"whisperModel": name})

    @_traced
    def set_brain(self, brain: str) -> dict:
        """Imposta brain ('claude'|'ollama'). Ritorna get_settings(). Se passa a 'ollama',
        prova ad avviarlo in background (best-effort) così è pronto senza intervento manuale."""
        updated = self.save_settings({"brain": brain})
        if brain == "ollama":
            self.start_ollama_autostart()
        return updated

    # --- modelli Ollama (G2) ------------------------------------------
    @_traced
    def list_ollama_models(self) -> list:
        """Lista modelli Ollama: installati (da /api/tags) + curated non-installati.
        Se Ollama non è in esecuzione ritorna solo il catalogo con isInstalled=False."""
        import httpx

        from vokari.llm.ollama_provider import is_up

        s = settings_mod.load()
        lang = i18n.normalize_lang(s.app_language)
        active = s.ollama_model
        endpoint = s.ollama_endpoint.rstrip("/")

        installed_names: set[str] = set()
        installed_sizes: dict[str, str] = {}

        if is_up(endpoint):
            try:
                r = httpx.get(f"{endpoint}/api/tags", timeout=5.0)
                if r.status_code == 200:
                    for m in r.json().get("models", []):
                        name = m.get("name", "")
                        if not name:
                            continue
                        installed_names.add(name)
                        size_b = m.get("size", 0)
                        if size_b >= 1_000_000_000:
                            installed_sizes[name] = f"{size_b / 1_000_000_000:.1f} GB"
                        elif size_b >= 1_000_000:
                            installed_sizes[name] = f"{size_b / 1_000_000:.0f} MB"
                        else:
                            installed_sizes[name] = "?"
            except Exception:  # noqa: S110 — calcolo dimensioni modelli, silenzioso ok
                pass

        result = []
        seen: set[str] = set()

        # modelli installati (inclusi quelli fuori dal catalogo curated); gli embedding
        # (nomic-embed-text, ...) non sanno generare briefing → esclusi dall'elenco cervelli.
        for name in sorted(installed_names):
            if _is_embedding_model(name):
                continue
            seen.add(name)
            curated = _match_curated(name)
            result.append(
                _ollama_entry(
                    name,
                    size_label=installed_sizes.get(name, curated["sizeLabel"] if curated else "?"),
                    curated=curated,
                    installed=True,
                    active=name == active,
                    lang=lang,
                )
            )

        # curated non ancora installati
        for c in _OLLAMA_CATALOG:
            if c["name"] not in seen:
                result.append(
                    _ollama_entry(
                        c["name"], size_label=c["sizeLabel"], curated=c, installed=False, active=False, lang=lang
                    )
                )

        return result

    @_traced
    def pull_ollama_model(self, name: str) -> dict:
        """Pull di un modello Ollama in background. Emette eventi ollama_pull
        (start → progress* → done|error). Ritorna subito per non bloccare il thread pywebview."""
        import httpx

        from vokari.llm.ollama_provider import is_up

        s = settings_mod.load()
        lang = i18n.normalize_lang(s.app_language)
        endpoint = s.ollama_endpoint.rstrip("/")

        def _do_pull() -> None:
            self._ollama_pull_cancel.discard(name)  # MOD1: ripulisci un flag stantio di un pull precedente
            self._emit("ollama_pull", {"name": name, "status": "start"})
            if not is_up(endpoint):
                self._emit(
                    "ollama_pull",
                    {
                        "name": name,
                        "status": "error",
                        "error": i18n.t("api.ollama_unreachable_run", lang),
                    },
                )
                return
            try:
                with httpx.stream(
                    "POST",
                    f"{endpoint}/api/pull",
                    json={"name": name, "stream": True},
                    timeout=httpx.Timeout(None, connect=10.0),
                ) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        # MOD1: annullamento richiesto da cancel_ollama_pull → chiudi lo stream
                        # (uscendo dal `with`) ed esci. Ollama conserva i blob già scaricati: il
                        # prossimo pull riprende da dove era arrivato.
                        if name in self._ollama_pull_cancel:
                            self._ollama_pull_cancel.discard(name)
                            self._emit("ollama_pull", {"name": name, "status": "cancelled"})
                            return
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if data.get("total"):
                            total = data["total"]
                            completed = data.get("completed", 0)
                            pct = min(0.99, completed / total) if total else 0.0
                            # MOD3: bytesDone/bytesTotal reali (Ollama li espone) → ETA lato frontend.
                            self._emit(
                                "ollama_pull",
                                {
                                    "name": name,
                                    "status": "progress",
                                    "pct": round(pct, 3),
                                    "bytesDone": completed,
                                    "bytesTotal": total,
                                },
                            )
                        elif data.get("status") == "success":
                            break
                self._emit("ollama_pull", {"name": name, "status": "done"})
            except Exception as e:
                debuglog.log_exc("ollama_pull_error", e, name=name)
                self._emit("ollama_pull", {"name": name, "status": "error", "error": str(e)})

        threading.Thread(target=_do_pull, daemon=True).start()
        return {"ok": True}

    @_traced
    def cancel_ollama_pull(self, name: str) -> dict:
        """MOD1: richiede l'interruzione di un pull Ollama in corso. Il worker `_do_pull` controlla
        questo flag tra una riga di progresso e l'altra, chiude lo stream HTTP ed emette
        `ollama_pull status=cancelled`. Ollama mantiene i blob già scaricati → il prossimo pull
        riprende. No-op se nessun pull con quel nome è attivo (il flag verrà ripulito al pull
        successivo). NB: il download Whisper NON è annullabile allo stesso modo — passa per la
        chiamata bloccante `huggingface_hub.snapshot_download`, senza hook di cancellazione."""
        self._ollama_pull_cancel.add(name)
        return {"ok": True}

    def _ollama_installed_bytes(self) -> int:
        """Byte totali dei modelli Ollama installati (best-effort via /api/tags). 0 se Ollama
        è giù o la query fallisce. Usato da disk_usage per il riepilogo 'GB usati dai modelli'."""
        import httpx

        from vokari.llm.ollama_provider import is_up

        s = settings_mod.load()
        endpoint = s.ollama_endpoint.rstrip("/")
        if not is_up(endpoint):
            return 0
        try:
            r = httpx.get(f"{endpoint}/api/tags", timeout=5.0)
            if r.status_code == 200:
                return sum(int(m.get("size", 0) or 0) for m in r.json().get("models", []))
        except Exception:  # noqa: S110 — riepilogo disco best-effort, silenzioso ok
            pass
        return 0

    @_traced
    def disk_usage(self) -> dict:
        """MOD3: riepilogo disco per la pill Modelli. usedByModelsGb = modelli Whisper (dir di
        VOKARI) + modelli Ollama installati; freeGb = spazio libero sul drive dei modelli Whisper.
        Disco in GB (10^9, convenzione dei dischi); 0.0 se non leggibile. Best-effort."""
        import shutil

        models_dir = ensure_dirs().models
        used = models_mod._dir_size(models_dir) + self._ollama_installed_bytes()
        try:
            free = shutil.disk_usage(str(models_dir)).free
        except OSError:
            free = 0
        return {"usedByModelsGb": round(used / 1e9, 1), "freeGb": round(free / 1e9, 1)}

    @_traced
    def delete_ollama_model(self, name: str) -> dict:
        """Elimina un modello Ollama locale (`DELETE /api/delete`)."""
        import httpx

        from vokari.llm.ollama_provider import is_up

        s = settings_mod.load()
        lang = i18n.normalize_lang(s.app_language)
        endpoint = s.ollama_endpoint.rstrip("/")

        if not is_up(endpoint):
            return {"ok": False, "error": i18n.t("api.ollama_unreachable", lang)}
        try:
            r = httpx.request("DELETE", f"{endpoint}/api/delete", json={"name": name}, timeout=30.0)
            return {"ok": r.status_code in (200, 204)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # --- gestione Ollama: VOKARI avvia/installa Ollama da sé ----------
    @_traced
    def ollama_status(self) -> dict:
        """Stato di Ollama per la UI: {installed, running, bundled, canInstall, endpoint}.
        installed = eseguibile presente (di sistema o bundled in userData); running = server up."""
        from app import ollama_manager

        s = settings_mod.load()
        data_dir = ensure_dirs().data
        return {
            "installed": ollama_manager.is_installed(data_dir),
            "running": ollama_manager.is_running(s.ollama_endpoint),
            "bundled": ollama_manager.bundled_exe(data_dir).is_file(),
            "canInstall": ollama_manager.can_auto_install(),
            "endpoint": s.ollama_endpoint,
        }

    @_traced
    def ollama_start(self) -> dict:
        """Avvia Ollama (di sistema o bundled) e attende che risponda. {ok, running}."""
        from app import ollama_manager

        s = settings_mod.load()
        ok = ollama_manager.start(ensure_dirs().data, s.ollama_endpoint)
        return {"ok": ok, "running": ok}

    @_traced
    def ollama_stop(self) -> dict:
        """Ferma i processi Ollama. {ok}."""
        from app import ollama_manager

        ollama_manager.stop()
        return {"ok": True}

    def ollama_install(self) -> dict:
        """Scarica+estrae Ollama (ZIP portabile, nessun admin) in background e lo avvia. Emette
        eventi `ollama_setup` (status downloading/starting/done/error, pct 0..1). Ritorna subito."""
        from app import ollama_manager

        s = settings_mod.load()
        lang = i18n.normalize_lang(s.app_language)

        def _do() -> None:
            data_dir = ensure_dirs().data
            self._emit("ollama_setup", {"pct": 0.0, "status": "downloading"})
            try:
                ollama_manager.download(
                    data_dir,
                    on_progress=lambda p: self._emit("ollama_setup", {"pct": round(p, 3), "status": "downloading"}),
                )
                self._emit("ollama_setup", {"pct": 1.0, "status": "starting"})
                ok = ollama_manager.start(data_dir, s.ollama_endpoint)
                self._emit(
                    "ollama_setup",
                    {"pct": 1.0, "status": "done"}
                    if ok
                    else {"pct": 1.0, "status": "error", "error": i18n.t("api.ollama_installed_not_started", lang)},
                )
            except Exception as e:
                debuglog.log_exc("ollama_install_error", e)
                self._emit("ollama_setup", {"pct": 0.0, "status": "error", "error": str(e)})

        threading.Thread(target=_do, daemon=True).start()
        return {"ok": True}

    def start_ollama_autostart(self) -> None:
        """All'avvio (chiamato da main.py): se l'organizzazione è su Ollama e il server è giù
        ma installato, lo avvia in un thread daemon (best-effort) — così l'utente non vede
        'Ollama non è in esecuzione'. Emette `ollama_setup` starting→done/error per la UI.
        NON installa (nessun download non richiesto). No-op se brain!=ollama, già up, o assente."""
        from app import ollama_manager

        s = settings_mod.load()
        lang = i18n.normalize_lang(s.app_language)
        if s.brain != "ollama" or ollama_manager.is_running(s.ollama_endpoint):
            return
        if not ollama_manager.is_installed(ensure_dirs().data):
            return

        def _do() -> None:
            self._emit("ollama_setup", {"pct": 1.0, "status": "starting"})
            ok = ollama_manager.start(ensure_dirs().data, s.ollama_endpoint)
            done = {"pct": 1.0, "status": "done"}
            err = {"pct": 1.0, "status": "error", "error": i18n.t("api.ollama_not_started", lang)}
            self._emit("ollama_setup", done if ok else err)

        threading.Thread(target=_do, daemon=True).start()

    # --- LibreHardwareMonitor (telemetria temperatura) ----------------
    def lhm_status(self) -> dict:
        """Ritorna {installed, running, canInstall}: usato dalla sezione LHM in Impostazioni.
        canInstall=False in MSIX (build Store) → la UI guida all'install manuale (ADR-046)."""
        from app import lhm_manager

        data_dir = ensure_dirs().data
        return {
            "installed": lhm_manager.is_installed(data_dir),
            "running": lhm_manager.is_running(),
            "canInstall": lhm_manager.can_auto_install(),
        }

    def lhm_install(self) -> dict:
        """Scarica LHM in background e lo avvia al termine. Emette lhm_progress via push
        (pct 0..1, status downloading/starting/done/error). Ritorna subito {ok: True}."""
        from app import lhm_manager

        def _do() -> None:
            data_dir = ensure_dirs().data
            self._emit("lhm_progress", {"pct": 0.0, "status": "downloading"})
            try:
                lhm_manager.download(
                    data_dir,
                    on_progress=lambda p: self._emit("lhm_progress", {"pct": round(p, 3), "status": "downloading"}),
                )
                self._emit("lhm_progress", {"pct": 1.0, "status": "starting"})
                lhm_manager.start(data_dir)
                self._emit("lhm_progress", {"pct": 1.0, "status": "done"})
            except Exception as e:
                debuglog.log_exc("lhm_install_error", e)
                self._emit("lhm_progress", {"pct": 0.0, "status": "error", "error": str(e)})

        threading.Thread(target=_do, daemon=True).start()
        return {"ok": True}

    def lhm_start(self) -> dict:
        """Avvia LHM con elevazione UAC. Ritorna {ok: True} se il processo è stato lanciato."""
        from app import lhm_manager

        ok = lhm_manager.start(ensure_dirs().data)
        return {"ok": ok}

    def lhm_stop(self) -> dict:
        """Termina LibreHardwareMonitor.exe."""
        from app import lhm_manager

        lhm_manager.stop()
        return {"ok": True}

    def lhm_uninstall(self) -> dict:
        """Ferma LHM e rimuove la cartella tools/lhm/."""
        from app import lhm_manager

        lhm_manager.uninstall(ensure_dirs().data)
        return {"ok": True}

    def lhm_debug(self) -> dict:
        """Dump diagnostico ACPI/OHM/LHM via PowerShell. Solo per sviluppo/debug."""
        import subprocess

        _DEBUG_PS = (
            "Write-Output 'ACPI:';"
            "$t=(Get-CimInstance -Namespace root/WMI -ClassName MSAcpi_ThermalZoneTemperature"
            " -ErrorAction SilentlyContinue).CurrentTemperature;"
            "if($t){Write-Output $t}else{Write-Output 'n/a'};"
            "foreach($ns in 'root/OpenHardwareMonitor','root/LibreHardwareMonitor'){"
            '  Write-Output "NS: $ns";'
            "  $s=Get-CimInstance -Namespace $ns -ClassName Sensor -ErrorAction SilentlyContinue"
            "  |Where-Object{$_.SensorType -eq 'Temperature'};"
            "  if($s){$s|Select-Object Name,Value|Format-Table -AutoSize|Out-String|Write-Output}"
            "  else{Write-Output 'n/a'}"
            "}"
        )
        try:
            _NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            r = subprocess.run(  # noqa: S603
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _DEBUG_PS],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=_NO_WIN,
            )
            return {"ok": True, "stdout": r.stdout, "stderr": r.stderr}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # --- registrazione ------------------------------------------------
    @_traced
    def list_sources(self) -> dict:
        try:
            mics = capture.list_input_devices()
        except RuntimeError:
            mics = []
        try:
            loop = capture.list_loopback_devices()
        except RuntimeError:
            loop = []
        return {"mic": mics, "system": loop}

    @_traced
    def start_recording(self, source: str, device=None) -> dict:
        # L14 — preflight spazio disco: la cattura scrive i WAV nativi in streaming nella
        # tempdir; a disco pieno l'audio si perde allo Stop. Controlliamo PRIMA di scartare la
        # registrazione precedente e di partire. 'critical' → solleva (App mostra ErrorScreen +
        # riprova, niente registrazione muta); 'low' → warning non bloccante, si registra.
        severity, minutes = capture.disk_preflight(source)
        if severity == "critical":
            raise RuntimeError(i18n.t("api.disk_full", self._lang(), minutes=max(0, int(minutes))))
        if severity == "low":
            self._emit("warning", {"messages": [i18n.t("api.disk_low", self._lang(), minutes=max(1, int(minutes)))]})

        # Guard: una registrazione precedente ancora attiva (doppio click sul REC, o
        # navigazione via da Live senza Stop) lascerebbe Recorder/LiveTranscriber orfani
        # (thread, stream WASAPI, modello). La scartiamo in un thread daemon: rec.stop() può
        # bloccare fino a _STOP_JOIN_TIMEOUT → non gelare il thread js-api di pywebview.
        prev_rec, prev_live = self._rec, self._live
        if prev_rec is not None or prev_live is not None:
            self._rec = None
            self._live = None

            def _discard_prev() -> None:
                if prev_live is not None:
                    try:
                        prev_live.stop()
                    except Exception as e:
                        debuglog.log_exc("discard_prev_live_error", e)
                if prev_rec is not None:
                    try:
                        prev_rec.stop()
                    except Exception as e:
                        debuglog.log_exc("discard_prev_rec_error", e)

            threading.Thread(target=_discard_prev, daemon=True).start()

        out = ensure_dirs().data / "recordings"
        out.mkdir(parents=True, exist_ok=True)
        wav = str(out / f"rec-{os.getpid()}-{threading.get_ident()}.wav")
        s = settings_mod.load()

        def _on_level(lane: str, db: float) -> None:
            # Livelli RMS reali per le onde/dB della schermata Live (push, ~10/s per lane).
            self._emit("audio_level", {"lane": lane, "db": round(db, 1)})

        on_audio = None
        self._live = None
        # Anteprima live solo se il modello live differisce dal principale: con lo stesso
        # nome `whisper._load_model` (lru_cache) restituirebbe la STESSA istanza WhisperModel
        # e LiveTranscriber + pipeline potrebbero usarla in concorrenza (faster-whisper non è
        # garantito thread-safe). Con modelli diversi la bozza ha anche senso (più veloce).
        if s.live_preview and s.live_model != s.whisper_model:
            from vokari.transcribe.live import (
                LiveTranscriber,
            )

            self._live = LiveTranscriber(
                model_name=s.live_model,
                language=s.transcription_language,
                on_text=lambda txt: self._emit("live_transcript", {"text": txt}),
            )
            self._live.start()
            _live_inst = self._live  # cattura l'istanza concreta (non self._live): stop_recording
            # azzera self._live sul thread js-api PRIMA che il thread mic finisca → None.feed crash

            def on_audio(block, rate):
                if _live_inst is not None:
                    _live_inst.feed(block, rate)

        self._rec = capture.Recorder(source, wav, device=device, on_level=_on_level, on_audio=on_audio)
        self._rec.start()
        return {"ok": True, "source": source}

    @_traced
    def add_marker(self, label: str) -> dict:
        if self._rec is None:
            return {"ok": False, "error": i18n.t("api.no_active_recording", self._lang())}
        return self._rec.add_marker(label)

    @_traced
    def update_marker(self, index: int, label: str) -> dict:
        """Aggiorna l'etichetta di un segnalibro già creato (editing inline in Live)."""
        if self._rec is None:
            return {"ok": False, "error": i18n.t("api.no_active_recording", self._lang())}
        m = self._rec.update_marker(int(index), label)
        return m if m is not None else {"ok": False, "error": i18n.t("api.bookmark_not_found", self._lang())}

    @_traced
    def cancel_recording(self) -> dict:
        """Annulla e scarta la registrazione corrente: nessun job creato.
        Ordine: rec.stop() PRIMA (join del thread mic) → poi live.stop().
        Il thread mic chiama on_audio/feed() fino al join: fermando il LiveTranscriber
        prima gli si passa audio da fermo (race I1)."""
        if self._rec is None:
            return {"ok": False, "error": i18n.t("api.no_active_recording", self._lang())}
        # Cattura in locali e azzera PRIMA di fermare (previene race con start_recording)
        rec = self._rec
        live = self._live
        self._rec = None
        self._live = None
        result = None
        try:
            result = rec.stop()
        except Exception:  # noqa: S110 — cancel: stop rec comunque, errore ok
            pass
        if live is not None:
            try:
                live.stop()
            except Exception:  # noqa: S110 — cancel: stop live comunque, errore ok
                pass
        # Pulisci il WAV scritto da Recorder.stop() (evita accumulo su sessioni cancellate)
        if result is not None:
            wav = getattr(result, "wav_path", None)
            if wav:
                try:
                    Path(wav).unlink(missing_ok=True)
                except OSError:
                    pass
        return {"ok": True}

    @_traced
    def pause_recording(self) -> dict:
        if self._rec is None:
            return {"ok": False, "error": i18n.t("api.no_active_recording", self._lang())}
        self._rec.pause()
        return {"ok": True, "paused": True}

    @_traced
    def resume_recording(self) -> dict:
        if self._rec is None:
            return {"ok": False, "error": i18n.t("api.no_active_recording", self._lang())}
        self._rec.resume()
        return {"ok": True, "paused": False}

    @_traced
    def stop_recording(self, mode: str | None = None, title: str | None = None, context: str | None = None) -> dict:
        if self._rec is None:
            return {"ok": False, "error": i18n.t("api.no_active_recording", self._lang())}
        # Catturiamo rec E live in locali SUBITO (sul thread js-api) e azzeriamo i campi:
        # _finalize gira in un thread daemon, e una nuova start_recording potrebbe riassegnare
        # self._live mentre la closure lo sta fermando (race → anteprima persa o None.feed).
        # Fermando il locale `live`, mai self._live, la finestra di race è chiusa.
        rec = self._rec
        live = self._live
        self._rec = None
        self._live = None
        s = settings_mod.load()
        # Job creato SUBITO (status queued, audio non ancora pronto): la GUI naviga a
        # processing e mostra "Finalizzo la registrazione…". La normalizzazione ffmpeg +
        # mix (lenta su registrazioni lunghe) gira in un thread daemon → niente freeze
        # del thread js-api di pywebview.
        job = self._store.create(
            Job.new(
                "",
                title=title or i18n.t("api.untitled_session", i18n.normalize_lang(s.app_language)),
                mode=mode or s.default_mode,
                context=context or "",
                status="queued",
                model=s.whisper_model,
                language=s.transcription_language,
            )
        )

        def _finalize() -> None:
            if live is not None:
                live.stop()
            try:
                result = rec.stop()
            except Exception as e:
                debuglog.log_exc("finalize_error", e, jobId=job.id)
                self._store.update(job.id, status="error", error=str(e))
                self._emit("status", {"jobId": job.id, "status": "error", "error": str(e)})
                return
            # A2: registra i livelli RMS per-lane + finale → il debug log spiega un'eventuale
            # 'both' muta (es. lane di sistema persa) senza dover indovinare.
            debuglog.log("capture_diagnostics", jobId=job.id, diagnostics=getattr(result, "diagnostics", {}))
            if getattr(result, "warnings", None):
                self._emit("warning", {"messages": result.warnings})
            updated = self._store.update(
                job.id, audio_path=result.wav_path, source=result.source, markers=result.markers
            )
            self._spawn_processing(updated)

        threading.Thread(target=_finalize, daemon=True).start()
        return {"jobId": job.id}

    def _error_job(self, message: str, *, title: str | None, mode: str | None) -> dict:
        """Crea un job in stato error + emette lo status: l'errore arriva sempre alla UI."""
        s = settings_mod.load()
        lang = i18n.normalize_lang(s.app_language)
        job = self._store.create(
            Job.new(
                "",
                title=title or i18n.t("api.untitled_session", lang),
                mode=mode or s.default_mode,
                status="error",
                error=message,
            )
        )
        self._emit("status", {"jobId": job.id, "status": "error", "error": message})
        return {"jobId": job.id, "error": message}

    @_traced
    def import_file(
        self, path: str, mode: str | None = None, title: str | None = None, context: str | None = None
    ) -> dict:
        # Gate (audit #6): rifiuta subito un file mancante/vuoto invece di scoprirlo a fine
        # pipeline dentro ffmpeg. La decodificabilità del formato resta gestita da
        # convert.to_wav_16k_mono (AudioConversionError) con messaggio chiaro.
        lang = i18n.normalize_lang(settings_mod.load().app_language)
        p = Path(path)
        if not p.is_file():
            debuglog.log("import_rejected", reason="missing")
            return {"error": i18n.t("api.file_not_found", lang)}
        try:
            empty = p.stat().st_size == 0
        except OSError:
            empty = False
        if empty:
            debuglog.log("import_rejected", reason="empty")
            return {"error": i18n.t("api.file_empty", lang)}
        # B3: senza titolo esplicito, derivalo dal nome del file (es. "183.m4a" → "183")
        if not title:
            title = p.stem or None
        return self._start_job(path, source="mic", mode=mode, title=title, context=context, markers=[])

    # --- elaborazione -------------------------------------------------
    def _start_job(
        self, audio_path: str, *, source: str, mode: str | None, title: str | None, context: str | None, markers: list
    ) -> dict:
        s = settings_mod.load()
        mode = mode or s.default_mode
        title = title or i18n.t("api.untitled_session", i18n.normalize_lang(s.app_language))
        job = self._store.create(
            Job.new(
                audio_path,
                title=title,
                mode=mode,
                context=context or "",
                source=source,
                model=s.whisper_model,
                language=s.transcription_language,
                markers=markers,
            )
        )
        self._spawn_processing(job)
        return {"jobId": job.id}

    def _spawn_processing(self, job: Job, skip_transcribe: bool = False) -> None:
        def run():
            try:
                result = pipeline_mod.run_processing(
                    job,
                    self._store,
                    emit=self._emit,
                    fit_gate=self._window is not None,
                    # N1: edit_gate attivo solo con GUI (come fit_gate) → la pipeline si ferma ad
                    # awaiting_edit per la revisione testo. Headless/test (_window None) proseguono.
                    # Sul resume skip_transcribe=True il gate non scatta comunque (ramo skip).
                    edit_gate=self._window is not None,
                    skip_transcribe=skip_transcribe,
                )
            except Exception:
                return
            # Caso 0-domande: la pipeline arriva a "ready" senza passare da generate()
            # → qui serve il salvataggio sessione (col percorso a domande resta in generate).
            if result is not None and result.status == "ready":
                try:
                    self._save_session(result)
                except Exception as e:
                    debuglog.log_exc("session_save_error", e, jobId=result.id)

        threading.Thread(target=run, daemon=True).start()

    def get_job(self, job_id: str) -> dict | None:
        job = self._store.get(job_id)
        return _job_view(job) if job else None

    def rename_job(self, job_id: str, title: str) -> dict:
        t = (title or "").strip()
        if not t:
            return {"ok": False}
        self._store.update(job_id, title=t)
        return {"ok": True}

    def get_active_job(self) -> dict | None:
        job = self._store.active()
        return _job_view(job) if job else None

    @_traced
    def resume_job(self, job_id: str) -> dict | None:
        job = self._store.get(job_id)
        if job:
            # N1: awaiting_edit → procedi con analisi (skippa trascrizione)
            if job.status == "awaiting_edit":
                self._spawn_processing(job, skip_transcribe=True)
            # Riprendi job midflight (queued, transcribing, etc.)
            elif job.status in ("queued", "transcribing", "analyzing", "rendering"):
                if not job.audio_path or not Path(job.audio_path).exists():
                    lang = i18n.normalize_lang(settings_mod.load().app_language)
                    error_msg = i18n.t("api.resume_file_missing", lang, path=job.audio_path or "—")
                    job = self._store.update(job_id, status="error", error=error_msg)
                    self._emit("status", {"jobId": job_id, "status": "error", "error": error_msg})
                else:
                    self._spawn_processing(job)
        return _job_view(job) if job else None

    @_traced
    def cancel_job(self, job_id: str) -> dict | None:
        job = self._store.get(job_id)
        if job:
            job = self._store.update(job_id, status="cancelled")
        return _job_view(job) if job else None

    @_traced
    def resolve_fit(self, job_id: str, decision: str) -> dict | None:
        """L08: l'utente ha deciso al gate del riassunto lossy. 'proceed' → registra il consenso
        e riprende la pipeline (che salta il gate, gate-once); 'cancel' (default difensivo) →
        annulla. No-op se il job non è fermo al gate (doppio click / stato già cambiato)."""
        job = self._store.get(job_id)
        if not job or job.status != "awaiting_fit_decision":
            return _job_view(job) if job else None
        if decision == "proceed":
            job = self._store.update(job_id, fit_decision="proceed", status="queued")
            # N1: se il transcript è già presente (gate A2 scattato DOPO il gate editing, o comunque
            # post-trascrizione) NON ritrascrivere — ricomincerebbe da capo scartando l'edit manuale
            # e ri-mostrando il gate editing. skip_transcribe=True usa il testo (eventualmente editato).
            self._spawn_processing(job, skip_transcribe=bool(job.transcript))
        else:
            job = self._store.update(job_id, status="cancelled")
            self._emit("status", {"jobId": job_id, "status": "cancelled"})
        return _job_view(job) if job else None

    def invalidate_transcript_cache(self, job_id: str) -> dict:
        """Invalida la cache di trascrizione per il job e re-accoda. Usato dal badge 'Rielabora'."""
        from vokari.transcribe.whisper import _cache_path, audio_hash

        job = self._store.get(job_id)
        if job is None:
            return {"ok": False, "error": "job not found"}
        key = f"{audio_hash(job.audio_path)}-{job.model}-{job.language}"
        cp = _cache_path(key)
        if cp.exists():
            cp.unlink()
        self._store.update(job_id, status="queued", pct=0.0, partial_text="", transcript="", error="")
        return {"ok": True}

    # --- N1: Transcript Editing ----------------------------------------

    @_traced
    def update_transcript(self, job_id: str, new_text: str) -> dict:
        """N1: salva il testo della trascrizione corretto a mano nella schermata di revisione e
        marca `transcript_edited` solo se davvero cambiato. Valido solo se il job è fermo al gate
        `awaiting_edit`; altri stati → {error} (validazione applicativa, NON una route HTTP). Non
        riprende la pipeline: la ripresa è esplicita via resume_job (l'utente clicca 'Procedi')."""
        job = self._store.get(job_id)
        if job is None:
            return {"error": i18n.t("api.job_not_found", self._lang(), sid=repr(job_id))}
        if job.status != "awaiting_edit":
            return {"error": i18n.t("api.transcript_not_editable", self._lang(), status=job.status)}
        edited = new_text != job.transcript
        self._store.update(job_id, transcript=new_text, transcript_edited=edited)
        return {"success": True}

    # --- intervista + briefing ----------------------------------------
    def get_questions(self, job_id: str) -> list:
        job = self._store.get(job_id)
        return [_question_view(q) for q in job.questions] if job else []

    @_traced
    def generate(self, job_id: str, answers: dict, skipped: list, extra_context: str = "") -> dict | None:
        """Avvia la generazione del briefing in un thread daemon e ritorna SUBITO il job
        corrente (status pre-generazione). La generazione include una chiamata LLM di
        refinement che può durare minuti: eseguirla nel thread js-api di pywebview
        congelerebbe la finestra (C1). Le transizioni (analyzing→rendering→ready, oppure
        error) arrivano alla UI via evento push `status`."""
        job = self._store.get(job_id)
        if not job:
            return None
        self._spawn_generate(job, answers or {}, skipped or [], extra_context or "")
        return _job_view(job)

    def _spawn_generate(self, job: Job, answers: dict, skipped: list, extra_context: str = "") -> None:
        def run():
            try:
                result = self._generate_impl(
                    job, self._store, answers, skipped, extra_context=extra_context, emit=self._emit
                )
            except Exception as e:
                debuglog.log_exc("generate_error", e, jobId=job.id)
                self._store.update(job.id, status="error", error=str(e))
                self._emit("status", {"jobId": job.id, "status": "error", "error": str(e)})
                return
            # Salva la sessione nella libreria quando il job diventa ready (ADR M7-F)
            if result.status == "ready":
                try:
                    self._save_session(result)
                except Exception as e:
                    debuglog.log_exc("session_save_error", e, jobId=job.id)

        threading.Thread(target=run, daemon=True).start()

    def _save_session(self, job: Job) -> None:
        """Persiste il job completato come Session nella libreria.

        B2: non salviamo sessioni vuote (nessun parlato trascritto) — eviterebbero solo
        di intasare la libreria di righe '00:00 / senza titolo'. Un job 'ready' ha sempre
        un transcript (E1 ferma quelli vuoti su 'error'), ma il guard è una difesa esplicita."""
        if not (job.transcript or "").strip():
            debuglog.log("session_save_skipped", jobId=job.id, reason="empty_transcript")
            return
        title = job.title or i18n.t(
            "api.untitled_session",
            i18n.normalize_lang(settings_mod.load().app_language),
        )
        session = Session(
            id=job.id,
            title=title,
            created_at=job.created_at or datetime.now(UTC).isoformat(),
            mode=job.mode,
            source=job.source,
            model=job.model,
            language=job.language,
            duration_ms=int(job.duration_s * 1000),
            transcript=job.transcript,
            word_count=len(job.transcript.split()) if job.transcript else 0,
            status="ready",
            audio_path=job.audio_path,
            markers=job.markers,
            analysis=job.analysis,
            da_chiarire=job.da_chiarire,
            briefing_path=job.briefing_path,
            artifacts={
                "briefing_md": job.briefing_md,
                "recap_md": job.recap_md,
                "obsidian_note": job.obsidian_note,
            },
        )
        self._sessions.save(session)

    # --- artefatti ----------------------------------------------------
    @_traced
    def get_artifacts(self, job_id: str) -> dict | None:
        job = self._store.get(job_id)
        if not job:
            return None
        return {
            "title": job.title,
            "briefingMd": job.briefing_md,
            "briefingPath": job.briefing_path,
            "recapMd": job.recap_md,
            "obsidianNote": job.obsidian_note,
            "transcriptText": job.transcript or "",
            "durationS": job.duration_s,
            "model": job.model,
            "language": job.language,
            "wordCount": len(job.transcript.split()) if job.transcript else 0,
        }

    # --- sessioni (F) ------------------------------------------------
    @_traced
    def list_sessions(self) -> list:
        """Lista sessioni completate ordinate per data (desc), shape camelCase."""
        return [_session_list_item(s) for s in self._sessions.list_all()]

    @_traced
    def search_sessions(self, q: str) -> list:
        """Ricerca full-text nelle sessioni salvate."""
        return [_session_list_item(s) for s in self._sessions.search(q)]

    @_traced
    def delete_session(self, session_id: str) -> dict:
        """Elimina una sessione dalla libreria + l'eventuale job persistito (resume).
        Ritorna {ok: True} se la sessione esisteva."""
        deleted = self._sessions.delete(session_id)
        try:
            self._store.delete(session_id)  # best-effort: session.id == job.id
        except Exception as e:
            debuglog.log_exc("job_delete_error", e, jobId=session_id)
        return {"ok": deleted}

    @_traced
    def delete_sessions(self, session_ids: list) -> dict:
        """Elimina più sessioni (+ job persistiti) in un colpo. Ritorna {ok, deleted}
        con il numero di sessioni effettivamente rimosse (gli id inesistenti sono ignorati)."""
        deleted = 0
        for sid in session_ids or []:
            if self._sessions.delete(sid):
                deleted += 1
            try:
                self._store.delete(sid)  # best-effort: session.id == job.id
            except Exception as e:
                debuglog.log_exc("job_delete_error", e, jobId=sid)
        return {"ok": True, "deleted": deleted}

    @_traced
    def play_session_audio(self, session_id: str) -> dict:
        """S2 (Livello A): apre l'audio della sessione nel lettore di sistema (come open_folder/
        open_url — niente streaming nella WebView, nessun problema di scheme `file://`). Ritorna
        {ok:False, error} se la sessione non esiste, non ha audio o il file è stato rimosso."""
        s = self._sessions.get(session_id)
        if not s or not s.audio_path:
            return {"ok": False, "error": i18n.t("api.audio_unavailable", self._lang())}
        p = Path(s.audio_path)
        if not p.exists():
            return {"ok": False, "error": i18n.t("api.audio_file_missing", self._lang())}
        try:
            os.startfile(str(p))  # Windows  # noqa: S606 — apre l'audio nel lettore di sistema
            return {"ok": True}
        except Exception as e:
            debuglog.log_exc("play_session_audio_error", e, jobId=session_id)
            return {"ok": False, "error": str(e)}

    @_traced
    def open_session(self, session_id: str) -> dict | None:
        """Carica una sessione dalla libreria e ritorna la shape Artifacts."""
        session = self._sessions.get(session_id)
        if not session:
            return None
        arts = session.artifacts or {}
        # briefingPath: preferisce session.briefing_path (durevole dopo re-export/L02),
        # fallback al job persistito (session.id == job.id) per sessioni pre-L02.
        job = self._store.get(session_id)
        briefing_path = session.briefing_path or (job.briefing_path if job else "")
        return {
            "title": session.title,
            "briefingMd": arts.get("briefing_md", ""),
            "briefingPath": briefing_path,
            "recapMd": arts.get("recap_md", ""),
            "obsidianNote": arts.get("obsidian_note", ""),
            "durationS": session.duration_ms / 1000 if session.duration_ms else 0.0,
            "model": session.model,
            "language": session.language,
            "wordCount": session.word_count or 0,
            "transcriptText": session.transcript or "",
        }

    # --- export artefatti (H) ----------------------------------------
    @_traced
    def export_pdf(self, job_id: str) -> dict:
        """Genera un PDF del recap e lo scrive accanto al briefing (o in briefing_dir).
        Ritorna {"ok": True, "path": ...} o {"ok": False, "error": ...}.

        Percorso normale: il job persistito (session.id == job.id). Fallback: se il job
        non c'è più ma esiste la Session, usa recap_md/title/audio_path della Session."""
        job = self._store.get(job_id)
        if job:
            title, recap_md, audio_path = job.title, job.recap_md, job.audio_path
        else:
            session = self._sessions.get(job_id)
            if not session:
                return {"ok": False, "error": i18n.t("api.job_not_found", self._lang(), sid=repr(job_id))}
            arts = session.artifacts or {}
            title, recap_md, audio_path = session.title, arts.get("recap_md", ""), session.audio_path
        out = self._choose_save_path(f"{_slug(title)}.recap.pdf", audio_path, ".recap.pdf")
        if out is None:
            return {"ok": False, "cancelled": True}  # dialogo annullato dall'utente
        try:
            pdf_mod.recap_md_to_pdf(recap_md or "", out)
            return {"ok": True, "path": out}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _choose_save_path(self, suggested_name: str, audio_path: str, suffix: str) -> str | None:
        """Path dove salvare un export. In app apre il SAVE dialog nativo (l'utente sceglie
        dove); ritorna None se annullato. Headless/test (niente dialog) → fallback su
        briefing_dir / accanto all'audio / userData. Il try/except copre i FakeWindow dei test."""
        if self._window is not None:
            try:
                res = self._window.create_file_dialog(_file_dialog("SAVE"), save_filename=suggested_name)
                chosen = res if isinstance(res, str) else (res[0] if res else "")
                return chosen or None  # "" / None = annullato
            except Exception:  # noqa: S110 — FakeWindow/backend senza dialog → fallback sotto
                pass
        s = settings_mod.load()
        if s.briefing_dir:
            d = Path(s.briefing_dir)
            d.mkdir(parents=True, exist_ok=True)
            return str(d / suggested_name)
        if audio_path:
            return str(Path(audio_path).with_suffix("")) + suffix
        return str(ensure_dirs().data / suggested_name)

    @_traced
    def save_text_file(self, content: str, suggested_name: str) -> dict:
        """Salva un artefatto testuale (briefing/recap/nota) dove sceglie l'utente (SAVE
        dialog). Ritorna {ok, path} oppure {ok:False, cancelled} se annullato."""
        out = self._choose_save_path(suggested_name, "", ".md")
        if out is None:
            return {"ok": False, "cancelled": True}
        try:
            Path(out).write_text(content or "", encoding="utf-8")
            return {"ok": True, "path": out}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @_traced
    def export_obsidian(self, job_id: str) -> dict:
        """Esporta le note Obsidian nel vault configurato.
        Ritorna {"ok": True, "count": n, "paths": [...]} o {"ok": False, "error": ...}."""
        lang = i18n.normalize_lang(settings_mod.load().app_language)
        job = self._store.get(job_id)
        session = None if job else self._sessions.get(job_id)
        if not job and not session:
            return {"ok": False, "error": i18n.t("api.job_not_found", lang, sid=repr(job_id))}
        try:
            s = settings_mod.load()
            if not s.obsidian_vault:
                return {"ok": False, "error": i18n.t("api.vault_not_configured", lang)}
            if job:
                # Percorso normale: re-render completo dall'analysis (sessione + note atomiche).
                analysis = Analysis.model_validate(job.analysis) if job.analysis else Analysis()
                notes = obsidian_mod.render_obsidian_notes(
                    analysis,
                    session_title=job.title,
                    session_date=analysis.meta.date if analysis.meta else "",
                    da_chiarire=job.da_chiarire,  # marcatori persistiti → note esportate complete
                    app_lang=lang,
                )
            else:
                # Fallback senza Job. Con l'Analysis persistita nella Session (L02) ri-renderizza
                # le note ATOMICHE complete (ancora + decisioni) dal JSON salvato verso il vault
                # corrente; altrimenti (sessioni pre-L02) scrivi la singola nota già renderizzata.
                if session.analysis:
                    analysis = Analysis.model_validate(session.analysis)
                    notes = obsidian_mod.render_obsidian_notes(
                        analysis,
                        session_title=session.title,
                        session_date=analysis.meta.date if analysis.meta else "",
                        da_chiarire=session.da_chiarire,
                        app_lang=lang,
                    )
                else:
                    arts = session.artifacts or {}
                    note_md = arts.get("obsidian_note", "")
                    if not note_md:
                        return {"ok": False, "error": i18n.t("api.no_obsidian_note", lang)}
                    filename = f"{obsidian_mod.safe(session.title)}.md"
                    notes = [obsidian_mod.ObsidianNote(filename, note_md)]
            written = obsidian_mod.export_to_vault(notes, s.obsidian_vault)
            return {"ok": True, "count": len(written), "paths": written}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @_traced
    def reexport_session(self, session_id: str) -> dict:
        """L02: rigenera briefing.md / recap.md / note Obsidian di una sessione salvata dal JSON
        Analysis PERSISTITO, scrivendoli nelle impostazioni CORRENTI (briefing_dir + vault). NESSUNA
        ri-trascrizione né chiamata LLM (render-only). Aggiorna gli artefatti congelati della Session
        e ritorna ExportResult {ok, path: briefing, count: n note, paths: [vault], error?}.

        Sessioni salvate prima di L02 non hanno `analysis` → errore esplicito (mai crash)."""
        s = settings_mod.load()
        lang = i18n.normalize_lang(s.app_language)
        session = self._sessions.get(session_id)
        if not session:
            return {"ok": False, "error": i18n.t("api.session_not_found", lang, sid=repr(session_id))}
        if not session.analysis:
            return {"ok": False, "error": i18n.t("api.reexport_no_analysis", lang)}
        try:
            analysis = Analysis.model_validate(session.analysis)
            source_name = Path(session.audio_path).name if session.audio_path else ""
            rendered = pipeline_mod.render_all_artifacts(
                analysis,
                title=session.title,
                source_name=source_name,
                transcription_model=session.model,
                llm_model=pipeline_mod.llm_label(s),
                session_id=session.id,
                transcript=session.transcript or "",
                da_chiarire=session.da_chiarire,
                markers=session.markers,
                language=("" if session.language in ("", "auto") else session.language),
                word_count=session.word_count or 0,
                app_lang=lang,
            )
            # briefing.md → briefing_dir corrente, altrimenti userData/data/briefings (azione di
            # libreria esplicita: non scriviamo accanto all'audio originale dell'utente).
            name = f"{_slug(session.title)}.briefing.md"
            briefing_dir = Path(s.briefing_dir) if s.briefing_dir else (ensure_dirs().data / "briefings")
            briefing_dir.mkdir(parents=True, exist_ok=True)
            briefing_path = briefing_dir / name
            briefing_path.write_text(rendered["briefing_md"], encoding="utf-8")
            # note Obsidian → vault corrente (se configurato)
            vault_paths: list[str] = []
            if s.obsidian_vault:
                vault_paths = obsidian_mod.export_to_vault(rendered["obsidian_notes"], s.obsidian_vault)
            # aggiorna gli artefatti congelati della Session (template/contenuto correnti)
            session.briefing_path = str(briefing_path)
            session.artifacts = {
                "briefing_md": rendered["briefing_md"],
                "recap_md": rendered["recap_md"],
                "obsidian_note": rendered["obsidian_note"],
            }
            self._sessions.save(session)
            return {"ok": True, "path": str(briefing_path), "count": len(vault_paths), "paths": vault_paths}
        except Exception as e:
            debuglog.log_exc("reexport_session_error", e, jobId=session_id)
            return {"ok": False, "error": str(e)}

    @_traced
    def browse_audio_file(self) -> dict:
        """Apre il file-picker nativo per scegliere un audio da importare."""
        if self._window is None:
            return {"path": ""}
        res = self._window.create_file_dialog(
            _file_dialog("OPEN"),
            allow_multiple=False,
            file_types=("Audio (*.mp3;*.wav;*.m4a;*.flac;*.ogg;*.aac)", "Tutti i file (*.*)"),
        )
        return {"path": res[0] if res else ""}

    @_traced
    def probe_audio(self, path: str) -> dict:
        """MDL2: metadati di un file audio da importare per il dialog di import (durata via
        ffprobe, peso da getsize). Best-effort: durationS=0 se ffprobe non legge la durata,
        sizeBytes=0 se il file non esiste → il dialog mostra solo ciò che conosce davvero
        (niente durata/peso inventati)."""
        from vokari.audio import convert as convert_mod

        dur = convert_mod.probe_duration_s(path) or 0.0
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        return {"durationS": round(dur, 1), "sizeBytes": size}

    def open_folder(self, path: str) -> dict:
        folder = os.path.dirname(path) or path
        try:
            os.startfile(folder)  # Windows  # noqa: S606 — apre Explorer per mostrare la cartella
            return {"ok": True}
        except (AttributeError, OSError) as e:
            return {"ok": False, "error": str(e)}
