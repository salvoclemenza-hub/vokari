"""Quanto un'analisi e' ancorata a cio' che e' stato DETTO.

Misura deterministica, nessun LLM. Due domande, una per difetto:

- **inventato**: nel briefing compaiono cifre o nomi propri che nella registrazione non ci
  sono? (ADR-066: il consolidamento ha prodotto due persone mai nominate, e `clean_entities`
  copre le sole entita' — idee, decisioni e prossimi passi non li guardava nessuno).
- **perso**: cifre che l'unione grezza delle finestre aveva estratto e che nel risultato
  finale non ci sono piu'.

Serve agli eval per dire se una modifica migliora o peggiora, e alla pipeline per AVVISARE.
Non cancella niente: segnalare un dubbio e' onesto, cancellare un elemento corretto no.
"""

import re
from typing import NamedTuple

from vokari.analyze import figures
from vokari.analyze.schema import Analysis

# Parola capitalizzata a meta' frase, oppure sigla tutta maiuscola: i candidati "nome proprio".
_NAME = re.compile(r"\b[A-ZÀ-Þ][a-zà-ÿ]{2,}\b|\b[A-Z]{2,}\b")
# Il primo token di un elemento e quello dopo un punto sono capitalizzati per convenzione:
# «Inviare il campione» non e' un nome proprio, e segnalarlo renderebbe tutto sospetto.
_SENTENCE_START = re.compile(r"(?:^|[.!?:;]\s+|\n)\s*\S+")
# Campi il cui valore E' un nome (non una frase): li' la prima parola e' il dato e va
# controllata. Perdonarla lascerebbe passare proprio la persona inventata di ADR-066.
_NAME_FIELDS = ("owner", "name")
_TEXT_FIELDS = ("purpose", "context")
_LIST_FIELDS = ("key_ideas", "decisions", "open_questions", "next_steps")


class Finding(NamedTuple):
    field: str
    text: str
    missing: list[str]


class Report(NamedTuple):
    n_final: int
    n_merged: int
    n_unsupported: int
    n_dropped: int
    grounding: float  # 1.0 = ogni elemento del risultato e' ancorato alla registrazione
    unsupported: list[Finding]
    dropped: list


def _text_of(item) -> str:
    """Il testo dell'elemento come lo legge una persona (per il report)."""
    if isinstance(item, str):
        return item
    return " ".join(str(v) for v in item.model_dump().values() if v)


def _parts_of(item) -> list[tuple[str, bool]]:
    """I pezzi da controllare separatamente: (testo, e' una frase).

    Un elemento strutturato concatena piu' campi: «Formato del calendario» + «Adottare un
    file Excel». Controllando la concatenazione, «Adottare» finisce a meta' frase e sembra
    un nome proprio - nella prima corsa vera dell'eval erano 5 avvisi su 5, tutti falsi.
    Ogni campo e' invece una frase a se', con la sua maiuscola di convenzione.
    """
    if isinstance(item, str):
        return [(item, True)]
    return [(str(v), k not in _NAME_FIELDS) for k, v in item.model_dump().items() if v]


def _names_in(text: str) -> set[str]:
    """Nomi propri e sigle, esclusi gli inizi di frase (capitalizzazione di convenzione)."""
    skip = {m.end() for m in _SENTENCE_START.finditer(text)}
    starts = {m.start() for m in _SENTENCE_START.finditer(text)}
    out = set()
    for m in _NAME.finditer(text):
        if m.start() in starts and m.end() in skip:
            continue  # e' la prima parola della frase
        out.add(m.group())
    return out


def _missing(
    text: str,
    transcript: str,
    transcript_low: str,
    transcript_figures: set[str],
    *,
    sentence: bool = True,
) -> list[str]:
    names = _names_in(text) if sentence else set(_NAME.findall(text))
    missing = [f for f in figures.figures_in(text) if f not in transcript_figures]
    missing += [n for n in names if n.lower() not in transcript_low]
    return missing


def _missing_in_item(item, transcript: str, transcript_low: str, transcript_figures: set[str]) -> list[str]:
    """Unisce i mancanti di ogni campo, senza ripetizioni e nell'ordine in cui compaiono."""
    out: list[str] = []
    for text, is_sentence in _parts_of(item):
        for m in _missing(text, transcript, transcript_low, transcript_figures, sentence=is_sentence):
            if m not in out:
                out.append(m)
    return out


def unsupported_items(analysis: Analysis, transcript: str) -> list[Finding]:
    """Elementi dell'analisi che contengono cifre o nomi assenti dalla registrazione."""
    if not (transcript or "").strip():
        return []
    low = " ".join(transcript.lower().split())
    figs = figures.figures_in(transcript)
    found: list[Finding] = []
    for field in _TEXT_FIELDS:
        text = getattr(analysis, field, "") or ""
        if text and (miss := _missing(text, transcript, low, figs)):
            found.append(Finding(field, text, miss))
    for field in _LIST_FIELDS:
        for item in getattr(analysis, field):
            text = _text_of(item)
            if text and (miss := _missing_in_item(item, transcript, low, figs)):
                found.append(Finding(field, text, miss))
    return found


def _count_items(a: Analysis) -> int:
    return sum(len(getattr(a, f)) for f in _LIST_FIELDS)


def report(transcript: str, *, merged: Analysis, final: Analysis) -> Report:
    """Fotografia della catena map-reduce: quanto e' ancorato e quanto si e' perso per strada."""
    unsupported = unsupported_items(final, transcript)
    dropped = figures.lost_items(merged, final)
    n_final = _count_items(final)
    grounding = 1.0 if n_final == 0 else max(0.0, 1.0 - len(unsupported) / n_final)
    return Report(
        n_final=n_final,
        n_merged=_count_items(merged),
        n_unsupported=len(unsupported),
        n_dropped=len(dropped),
        grounding=round(grounding, 3),
        unsupported=unsupported,
        dropped=dropped,
    )
