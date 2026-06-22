"""Rifinitura bounded (spec §9): l'LLM rileva le lacune e genera max 3-5 domande
skippabili. Le risposte arricchiscono l'analisi; le saltate/vuote diventano marcatori
[DA CHIARIRE] nel briefing.
"""

from pydantic import BaseModel, ConfigDict, Field

from vokari.analyze.schema import Analysis

MAX_QUESTIONS = 5
_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

_SYSTEM = (
    "Sei un intervistatore che migliora un briefing generato da una registrazione. "
    "Rileva SOLO le lacune REALI, in questo ORDINE DI PRIORITÀ (chiedi prima le più importanti): "
    "1) numeri, quantità, date o fatti in CONTRADDIZIONE tra loro (es. due budget diversi): "
    "chiedi quale vale CITANDO entrambi i valori; "
    "2) decisioni aperte o prese senza motivazione; "
    "3) prossimi passi senza responsabile o senza scadenza; "
    "4) rischi, ostacoli o dipendenze non valutati; "
    "5) SOLO se manca altro di più importante: sigle non spiegate, persone senza ruolo, gergo. "
    "Ancora OGNI domanda a un dettaglio concreto del testo (cita il valore/nome/punto preciso). "
    "Genera al massimo 5 domande, dalla più importante alla meno. "
    "Regole: ogni domanda <= 12 parole, dai del 'tu', niente domande già rispondibili dal testo, "
    "niente domande ovvie o di pura curiosità. Rispondi ESCLUSIVAMENTE con JSON valido, nessun "
    "code fence, nessuna spiegazione. "
    "IMPORTANTE: usa la stessa lingua della trascrizione (es. italiano se il testo è in italiano)."
)

_SHAPE = """Produci ESATTAMENTE questo JSON:
{"questions": [
  {"id": "q1", "text": "<domanda <=12 parole, ancorata a un dettaglio del testo>", "priority": "high|medium|low",
   "suggestions": ["<chip breve>", "..."],
   "why": "<perché la chiedi, <=12 parole, NON ripetere la domanda>",
   "fromAudio": true}
]}
0-3 suggestions per domanda. "why" = il motivo (es. "trovata una possibile contraddizione",
"riferimento temporale in sospeso"). "fromAudio" = true se la domanda nasce da un dettaglio
CITATO nel testo, false se è di metodo (es. "per chi è il briefing?"). Se non ci sono lacune,
"questions": []."""

# Few-shot: insegna al modello (soprattutto a quelli locali piccoli) la GERARCHIA di valore —
# una CONTRADDIZIONE sui numeri e una decisione aperta PRIMA del ruolo di una persona — e ad
# ANCORARE la domanda al valore preciso citandolo (chip = le opzioni concrete).
_FEWSHOT = """ESEMPIO (tipo di domande attese, dalla più importante; ancorate ai dettagli):
Trascrizione: "Il budget è 700 euro... anzi parliamo di 730 euro dilazionati. Dobbiamo decidere
se lanciare a marzo o aprile. Marco si occupa del sito."
JSON:
{"questions": [
  {"id": "q1", "text": "Budget 700 o 730 euro?", "priority": "high", "suggestions": ["700", "730"],
   "why": "i due importi si contraddicono", "fromAudio": true},
  {"id": "q2", "text": "Lanciate a marzo o aprile?", "priority": "high", "suggestions": ["Marzo", "Aprile"],
   "why": "decisione ancora aperta", "fromAudio": true},
  {"id": "q3", "text": "Marco con quale ruolo sul sito?", "priority": "low", "suggestions": ["Sviluppo", "Contenuti"],
   "why": "ruolo non specificato", "fromAudio": true}
]}
(La contraddizione sul budget e la decisione aperta vengono PRIMA del ruolo di Marco.)"""


class Question(BaseModel):
    # populate_by_name + alias: accetta sia from_audio (nome campo) sia fromAudio (alias) dal JSON
    # dell'LLM — i modelli locali a volte camelCasano. model_dump() resta snake (from_audio).
    model_config = ConfigDict(populate_by_name=True)
    id: str
    text: str
    priority: str = "medium"
    suggestions: list[str] = Field(default_factory=list)
    why: str = ""  # I1: perché la domanda (rationale); opzionale → l'LLM può non popolarlo
    from_audio: bool = Field(default=False, alias="fromAudio")  # I2: nata da un dettaglio del testo


def _build_user(analysis: Analysis, transcript: str, mode: str) -> str:
    return "\n".join(
        [
            f"Tipo sessione: {mode}.",
            _SHAPE,
            "",
            _FEWSHOT,
            "",
            "ANALISI CORRENTE (JSON):",
            analysis.model_dump_json(),
            "",
            "TRASCRIZIONE:",
            transcript,
        ]
    )


def _norm_q(text: str) -> str:
    """Normalizza per il confronto: minuscole, senza spazi/punteggiatura ai bordi."""
    return text.strip().lower().rstrip("?.! ").strip()


def detect_questions(
    analysis: Analysis, transcript: str, *, provider, mode: str = "solo", should_cancel=None
) -> list[Question]:
    user = _build_user(analysis, transcript, mode)
    # P4 (anti-timeout): usa lo streaming se il provider lo espone (come l'analyzer) — il
    # read-timeout si resetta a ogni token, quindi non scatta mentre il modello genera. Fallback
    # a chat_json per i provider che non lo implementano (fake nei test): stesso cardine
    # hasattr(provider, "chat_json_stream") dell'analyzer (lezione ADR-010/036). should_cancel
    # interrompe la generazione a metà (la chiamata è leggera grazie a P2, ma resta onorata).
    if hasattr(provider, "chat_json_stream"):
        raw = provider.chat_json_stream(_SYSTEM, user, should_cancel=should_cancel)
    else:
        raw = provider.chat_json(_SYSTEM, user)
    items = raw.get("questions", []) if isinstance(raw, dict) else []
    qs = [Question.model_validate(q) for q in items]
    qs.sort(key=lambda q: _PRIORITY_ORDER.get(q.priority, 1))
    # dedup per testo normalizzato (l'LLM a volte ripete la stessa domanda) E scarto ciò che è
    # GIÀ una domanda aperta dell'analisi: inutile richiedere a voce ciò che il briefing marca
    # già come aperto (spreca l'unico momento interattivo).
    seen: set[str] = {_norm_q(oq) for oq in analysis.open_questions}
    deduped: list[Question] = []
    for q in qs:
        key = _norm_q(q.text)
        if key and key not in seen:
            seen.add(key)
            deduped.append(q)
    return deduped[:MAX_QUESTIONS]


def build_refinement(questions: list[Question], answers: dict[str, str], skipped: list[str]) -> dict[str, str]:
    """Dict PIATTO {testo_domanda: risposta} per prompts.build_user — solo risposte
    valorizzate e non saltate."""
    out: dict[str, str] = {}
    for q in questions:
        a = (answers.get(q.id) or "").strip()
        if a and q.id not in skipped:
            out[q.text] = a
    return out


def da_chiarire_markers(questions: list[Question], answers: dict[str, str], skipped: list[str]) -> list[str]:
    """Domande saltate o vuote -> marcatori [DA CHIARIRE] (passati a render_briefing)."""
    out: list[str] = []
    for q in questions:
        a = (answers.get(q.id) or "").strip()
        if q.id in skipped or not a:
            out.append(f"{q.text} (domanda saltata in rifinitura)")
    return out
