"""Le CIFRE di un briefing non si perdono per strada.

Il consolidamento (`analyzer._consolidate`) riordina e accorpa gli elementi estratti dalle
finestre: e' cio' che lo rende leggibile, ed e' anche cio' che lo rende pericoloso. Misurato
il 24/09/2026 su una registrazione reale (map `qwen2.5:7b`, reduce `granite4.2:8b`): il
briefing e' passato da 9 a 23 elementi, ma nel riordino sono sparite una data di
presentazione e una forbice di prezzo min-max.

Un numero e' la parte di un briefing che nessuno ricostruisce a memoria. Qui il controllo e'
DETERMINISTICO — nessun LLM, nessun costo: se un elemento dell'unione grezza conteneva una
cifra e quella cifra non compare da nessuna parte nella lista consolidata, l'elemento
originale torna in coda. Le voci SENZA cifre non si toccano: accorparle e' esattamente il
lavoro che il consolidamento deve poter fare.
"""

import re

from vokari.analyze.schema import Analysis

# «1.200» / «1 200» (migliaia) oppure «1,5» / «3.14» (decimale) oppure un intero.
# Mai attaccato a lettere: «v2», «qwen2.5», «finestra-1» sono nomi, non dati.
_NUM = re.compile(r"(?<![A-Za-zÀ-ÿ])(?:\d{1,3}(?:[.\u00a0 ]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)(?![A-Za-zÀ-ÿ])")


def _normalize(raw: str) -> str:
    """«1.200» e «1200» sono lo stesso numero; «1,5» resta distinto da «15»."""
    if re.fullmatch(r"\d{1,3}(?:[.\u00a0 ]\d{3})+(?:,\d+)?", raw):
        intero, _, dec = raw.partition(",")
        intero = re.sub(r"[.\u00a0 ]", "", intero)
        return f"{intero}.{dec}" if dec else intero
    return raw.replace(",", ".")


def figures_in(text: str) -> set[str]:
    """Insieme normalizzato delle cifre presenti nel testo (numeri, percentuali, date).

    Le cifre singole (`1`, `7`) sono escluse: sono quasi sempre numerazioni o frammenti di
    identificatori, e riportarle indietro riempirebbe il briefing di rumore. Si perde
    qualche «3 giorni»; si guadagna che il controllo resta credibile."""
    out = {_normalize(m.group()) for m in _NUM.finditer(text or "")}
    return {f for f in out if len(f) > 1}


_FIELDS = ("key_ideas", "decisions", "open_questions", "next_steps")


def _text_of(item) -> str:
    """Tutto il testo di un elemento, qualunque sia la sua forma (str o modello)."""
    if isinstance(item, str):
        return item
    return " ".join(str(v) for v in item.model_dump().values() if v)


def lost_items(merged: Analysis, consolidated: Analysis) -> list:
    """Elementi di `merged` le cui cifre non compaiono piu' in `consolidated`. Puro: non
    tocca niente, serve a CONTARE (gli eval) oltre che a correggere."""
    lost: list = []
    for field in _FIELDS:
        present: set[str] = set()
        for item in getattr(consolidated, field):
            present |= figures_in(_text_of(item))
        for item in getattr(merged, field):
            wanted = figures_in(_text_of(item))
            if wanted and not (wanted & present):
                lost.append(item)
                present |= wanted
    return lost


def restore_lost_figures(merged: Analysis, consolidated: Analysis) -> list:
    """Rimette in `consolidated` gli elementi di `merged` le cui cifre sono sparite.

    Muta `consolidated` (come il resto della catena di analisi) e restituisce la lista degli
    elementi ripristinati, cosi' il chiamante puo' dirlo a chi guarda invece di farlo di
    nascosto."""
    restored: list = []
    for field in _FIELDS:
        out = getattr(consolidated, field)
        present: set[str] = set()
        for item in out:
            present |= figures_in(_text_of(item))
        for item in getattr(merged, field):
            wanted = figures_in(_text_of(item))
            if wanted and not (wanted & present):
                out.append(item)
                present |= wanted
                restored.append(item)
    return restored
