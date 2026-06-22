"""Provider LLM locale via Ollama (API /api/chat). Modalità offline opzionale."""

import json
import shutil
import subprocess
import sys
import time

import httpx

from vokari.llm.base import LLMError, parse_json_lenient

# Timeout chiamate /api/chat. READ generoso (600s) perché su CPU (AMD, nessuna GPU) una
# chiamata su trascrizione lunga + caricamento modello a freddo può durare minuti: 240s
# tagliava chiamate legittime (è la causa del timeout ECO 5.0 su detect_questions). Con lo
# streaming (chat_json_stream, usato da analyzer e detect_questions) il read-timeout si resetta
# a ogni token, quindi questo valore è solo una RETE DI SICUREZZA contro Ollama davvero appeso;
# il connect breve fa fallire in fretta se il server è morto. La cancellazione durante la
# chiamata è onorata via should_cancel nello streaming + check status al confine-step.
_TIMEOUT = httpx.Timeout(600.0, connect=10.0)


def is_up(endpoint: str) -> bool:
    """True se il server Ollama risponde su {endpoint}/api/tags."""
    try:
        r = httpx.get(f"{endpoint.rstrip('/')}/api/tags", timeout=2.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def ensure_available(endpoint: str, *, timeout: float = 20.0) -> bool:
    """Garantisce che Ollama sia raggiungibile. Se è giù prova ad avviarlo da solo
    (`ollama serve`, se l'eseguibile è nel PATH) e attende fino a `timeout` secondi che
    risponda. Ritorna True se (ri)attivo, False se non installato o non riparte.

    Evita di far trascrivere un'ora di audio per poi fallire all'analisi: il chiamante
    (pipeline) lo invoca PRIMA della trascrizione."""
    base = endpoint.rstrip("/")
    if is_up(base):
        return True
    exe = shutil.which("ollama")
    if not exe:
        return False
    try:
        kwargs = {}
        if sys.platform.startswith("win"):
            # CREATE_NO_WINDOW | DETACHED_PROCESS: nessuna console, staccato dalla GUI.
            kwargs["creationflags"] = 0x08000000 | 0x00000008
        subprocess.Popen(  # noqa: S603 — exe validato da shutil.which, avvio ollama serve locale
            [exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
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


# Dimensionamento finestra di contesto (num_ctx). Ollama usa di default num_ctx=2048 token
# e TRONCA in silenzio i prompt più lunghi: su una trascrizione reale (~1600 parole, prompt
# ~3400+ token) il modello perde la coda e collassa i campi più "lontani" dell'analisi
# (open_questions/next_steps/entities) a liste VUOTE, pur riempendo le stringhe (purpose/
# context). Repro: stesso prompt, num_ctx 2048 → liste vuote, num_ctx 8192 → estrazione
# completa. Quindi dimensioniamo num_ctx sul prompt FINO al massimo reale del modello (letto
# da /api/show); oltre quel massimo è l'analyzer a riassumere (mai troncare in silenzio).
_CTX_MIN = 4096  # alza il default pericoloso (2048) a un minimo sicuro
_CTX_OUTPUT_HEADROOM = 2048  # token riservati all'output JSON dell'analisi
_CHARS_PER_TOKEN = 3  # stima conservativa per l'italiano (sovrastima i token → ctx più ampio)
_CTX_FALLBACK_MAX = 8192  # se /api/show non risponde: cap prudente (l'analyzer riassume oltre)
# Scaglioni di num_ctx: si sale solo quanto serve (KV cache = RAM+tempo su CPU), fino al max modello.
_CTX_BUCKETS = (4096, 8192, 16384, 32768, 65536, 131072)


def _num_ctx_for(system: str, user: str, hard_max: int) -> int:
    """num_ctx sufficiente per prompt + output, salito a scaglioni e clampato a `hard_max`
    (il massimo reale del modello). Non scende sotto _CTX_MIN."""
    approx = (len(system) + len(user)) // _CHARS_PER_TOKEN + _CTX_OUTPUT_HEADROOM
    for ctx in _CTX_BUCKETS:
        if ctx >= hard_max:
            return hard_max
        if approx <= ctx:
            return ctx
    return hard_max


def _ollama_http_error_message(endpoint: str, e: httpx.HTTPError) -> str:
    """Messaggio onesto: connect-fail (server giù) vs read-timeout (modello lento ma VIVO). Il
    vecchio 'non raggiungibile' era fuorviante sui read-timeout — è la diagnosi sbagliata del
    caso ECO 5.0 (1s prima dell'errore la telemetria segnava CPU 57%: Ollama stava ancora
    generando, non era morto)."""
    if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout)):
        return f"Ollama non raggiungibile su {endpoint} — avvialo o passa a Claude nelle Impostazioni."
    if isinstance(e, (httpx.ReadTimeout, httpx.PoolTimeout)):
        mins = max(1, int((_TIMEOUT.read or 0) // 60))
        return (
            f"Ollama è attivo ma la risposta ha superato {mins} min: il modello è lento su CPU. "
            "Usa un modello più piccolo, abbrevia la registrazione, o passa a Claude."
        )
    return f"Ollama non raggiungibile su {endpoint}: {e}"


class OllamaProvider:
    def __init__(self, endpoint: str, model: str):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self._max_ctx: int | None = None  # cache SOLO del valore REALE (mai del fallback)
        self._ctx_is_fallback: bool = True  # True finché non si legge un max reale da /api/show

    def model_max_ctx(self) -> int:
        """Massima finestra di contesto del modello in token (es. qwen2.5:7b → 32768), letta da
        /api/show e cachata SOLO se reale. Se /api/show non risponde (Ollama in avvio) ritorna un
        fallback prudente (_CTX_FALLBACK_MAX) ma NON lo cacha: ritenta alla chiamata successiva —
        altrimenti una singola lettura fallita bloccherebbe l'istanza a 8192 per sempre, facendo
        riassumere inutilmente anche su qwen (32k). Serve sia a dimensionare num_ctx fino al vero
        limite, sia a far decidere all'analyzer quando riassumere (context_budget_tokens)."""
        if self._max_ctx is not None:
            return self._max_ctx
        val: int | None = None
        try:
            r = httpx.post(
                f"{self.endpoint}/api/show",
                json={"name": self.model},
                timeout=httpx.Timeout(10.0, connect=5.0),
            )
            r.raise_for_status()
            info = r.json().get("model_info") or {}
            # la chiave è "<arch>.context_length" (es. "qwen2.context_length")
            for k, v in info.items():
                if k.endswith(".context_length") and isinstance(v, int) and v > 0:
                    val = v
                    break
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            pass  # Ollama giù o risposta inattesa: ritorna il fallback ma NON cacharlo
        if val is not None:
            self._max_ctx = val  # cacha SOLO il valore reale
            self._ctx_is_fallback = False
            return val
        self._ctx_is_fallback = True
        return _CTX_FALLBACK_MAX

    def ctx_diagnostics(self, system: str = "", user: str = "") -> dict:
        """Diagnostica del dimensionamento contesto: massimo reale del modello, se è caduto sul
        fallback (Ollama in avvio / /api/show non disponibile), e il num_ctx che verrebbe
        pianificato per (system,user). Alimenta FitReport (check idoneità) e un eventuale
        log/badge 'qwen2.5:7b · ctx 32768 · num_ctx 32768'."""
        ctx_max = self.model_max_ctx()  # aggiorna _ctx_is_fallback come effetto
        return {
            "model": self.model,
            "ctx_max": ctx_max,
            "ctx_is_fallback": self._ctx_is_fallback,
            "num_ctx_planned": _num_ctx_for(system, user, ctx_max),
        }

    def context_budget_tokens(self) -> int:
        """Max token di INPUT per una singola analisi, lasciando spazio all'output. L'analyzer
        riassume (con warning) le trascrizioni oltre questo budget, invece di lasciarle troncare
        in silenzio dal num_ctx di Ollama."""
        return max(_CTX_MIN, self.model_max_ctx() - _CTX_OUTPUT_HEADROOM)

    def _payload(self, system: str, user: str, *, json_mode: bool, json_schema: dict | None, stream: bool) -> dict:
        # num_ctx SEMPRE dimensionato (anche per chat_text, usato dal riepilogo a chunk):
        # il default 2048 di Ollama tronca i prompt lunghi → analisi con liste vuote.
        options: dict = {"num_ctx": _num_ctx_for(system, user, self.model_max_ctx())}
        payload: dict = {
            "model": self.model,
            "stream": stream,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": options,
        }
        if json_mode:
            if json_schema and "$defs" not in json_schema and "$ref" not in json_schema:
                # Structured outputs Ollama 0.5+ (constrained decoding llama.cpp):
                # richiede schema flat senza $defs/$ref — Pydantic model_json_schema()
                # per modelli annidati produce $defs, quindi passiamo solo schema flat.
                payload["format"] = json_schema
            else:
                # "format":"json" = JSON valido; il few-shot nel prompt guida la struttura.
                # Usato quando lo schema contiene $defs/$ref (es. Analysis di Pydantic v2)
                # che llama.cpp non risolve e che causerebbero output malformato.
                payload["format"] = "json"
            # temperature:0 rende l'output deterministico — utile per strutture JSON fisse.
            options["temperature"] = 0
        return payload

    def _chat(self, system: str, user: str, *, json_mode: bool = False, json_schema: dict | None = None) -> str:
        payload = self._payload(system, user, json_mode=json_mode, json_schema=json_schema, stream=False)
        try:
            r = httpx.post(
                f"{self.endpoint}/api/chat",
                json=payload,
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMError(_ollama_http_error_message(self.endpoint, e)) from e
        try:
            return r.json()["message"]["content"].strip()
        except (KeyError, TypeError, ValueError) as e:
            raise LLMError(f"Ollama ha restituito una risposta inattesa: {e}") from e

    def chat_json(self, system: str, user: str, *, json_schema: dict | None = None) -> dict:
        return parse_json_lenient(self._chat(system, user, json_mode=True, json_schema=json_schema))

    def chat_text(self, system: str, user: str) -> str:
        return self._chat(system, user)

    def chat_json_stream(
        self,
        system: str,
        user: str,
        *,
        json_schema: dict | None = None,
        on_delta=None,
        should_cancel=None,
    ) -> dict:
        # /api/chat con stream=True: risposta NDJSON, una riga JSON per chunk con
        # message.content (delta) e done (bool). Accumuliamo il contenuto, esponiamo i delta
        # via on_delta, e parsiamo a fine stream — stesso risultato di chat_json.
        payload = self._payload(system, user, json_mode=True, json_schema=json_schema, stream=True)
        acc = ""
        cancelled = False
        try:
            with httpx.stream("POST", f"{self.endpoint}/api/chat", json=payload, timeout=_TIMEOUT) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue  # riga NDJSON malformata: salta, non far fallire l'intero stream
                    acc += obj.get("message", {}).get("content", "")
                    if on_delta:
                        on_delta(acc)
                    if obj.get("done"):
                        break
                    if should_cancel and should_cancel():
                        cancelled = True
                        break
        except httpx.HTTPError as e:
            raise LLMError(_ollama_http_error_message(self.endpoint, e)) from e
        if cancelled:
            # Annullato a metà: oggetto vuoto (Analysis defaultato valido); il chiamante
            # rileva la cancellazione al confine-step e scarta comunque l'analisi.
            return {}
        return parse_json_lenient(acc)
