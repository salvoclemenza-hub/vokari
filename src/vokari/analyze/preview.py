"""Rende leggibile il JSON PARZIALE che arriva in streaming durante l'analisi.

Durante la fase 'analyzing' l'LLM produce un oggetto JSON (schema `Analysis`) un token
alla volta. Mostrare il JSON grezzo (graffe, virgolette, nomi di campo) sarebbe illeggibile;
mostrare i soli VALORI testuali man mano che compaiono dà l'effetto "il briefing prende forma".

`preview_from_partial_json` è uno scanner TOLLERANTE (niente `json.loads`): funziona su input
TRONCATO a qualunque punto, non solleva mai, e include anche l'ultima stringa non ancora chiusa
(la frase che il modello sta scrivendo). Salta le chiavi e il blocco `meta` (rumore: type/title/date).
"""

# Sezioni di primo livello i cui valori NON vanno mostrati (rumore strutturale).
_SKIP_SECTIONS = {"meta"}

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/"}


def _read_string(raw: str, start: int) -> tuple[str, int, bool]:
    """Legge una stringa JSON a partire dalla virgoletta di apertura `raw[start] == '"'`.

    Ritorna (contenuto_decodificato, indice_dopo_la_stringa, chiusa?). Se la stringa non è
    chiusa (stream troncato), `chiusa` è False e l'indice è la fine dell'input.
    """
    buf: list[str] = []
    j = start + 1
    n = len(raw)
    while j < n:
        ch = raw[j]
        if ch == "\\" and j + 1 < n:
            buf.append(_ESCAPES.get(raw[j + 1], raw[j + 1]))
            j += 2
            continue
        if ch == '"':
            return "".join(buf), j + 1, True
        buf.append(ch)
        j += 1
    return "".join(buf), n, False  # troncata: stringa in corso di scrittura


def preview_from_partial_json(raw: str) -> str:
    """Estrae i valori stringa leggibili da un JSON (anche parziale), uno per riga.

    - Salta le CHIAVI (un campo è chiave se la stringa, chiusa, è in posizione-chiave).
    - Salta i valori sotto le sezioni in `_SKIP_SECTIONS` (es. `meta`).
    - Include l'ultima stringa-valore anche se non chiusa; una chiave non chiusa (nome di
      campo in scrittura) NON viene mostrata.
    """
    values: list[str] = []
    stack: list[str] = []  # 'obj' | 'arr'
    expect_key = False
    section: str | None = None  # chiave corrente a profondità 1 (root)
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == '"':
            s, nxt, closed = _read_string(raw, i)
            is_key = expect_key and bool(stack) and stack[-1] == "obj"
            if is_key:
                if closed:
                    if len(stack) == 1:
                        section = s
                    expect_key = False  # seguirà ':'
                # chiave non chiusa → in scrittura: non mostrarla
            elif s.strip() and section not in _SKIP_SECTIONS:
                values.append(s)  # valore (chiuso o ultimo troncato)
            i = nxt
            continue
        if c == "{":
            stack.append("obj")
            expect_key = True
        elif c == "[":
            stack.append("arr")
            expect_key = False
        elif c in "}]":
            if stack:
                stack.pop()
            if not stack:
                section = None
            expect_key = False
        elif c == ":":
            expect_key = False
        elif c == ",":
            expect_key = bool(stack) and stack[-1] == "obj"
        i += 1
    return "\n".join(values)
