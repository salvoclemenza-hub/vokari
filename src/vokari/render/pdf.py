"""Renderer recap.md -> PDF (spec M7/H).

Usa fpdf2 con font core (Helvetica/Courier) per evitare dipendenze esterne.
I caratteri non-latin1 frequenti in italiano vengono normalizzati da `_sanitize`.
`multi_cell(markdown=True)` abilita **bold** inline (fpdf2 feature).
`_strip_italic` rimuove _..._ (markdown italic non supportato da fpdf2).
"""

from __future__ import annotations

import os
import re

from fpdf import FPDF

# Font TTF Unicode (regular, bold): se presenti sul sistema rendono €, —, • e accenti
# NATIVAMENTE (niente translitterazione). L'app gira su Windows → preferisci i font di
# sistema; fallback DejaVu (Linux/CI). Se nessuno è presente → core Helvetica + _sanitize.
_FONT_PAIRS = [
    (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def _try_unicode_font(pdf: FPDF) -> str | None:
    """Registra il primo font TTF Unicode (regular+bold) disponibile e ne ritorna il nome
    famiglia ("vk"). None se nessuno è presente → il chiamante usa il core latin-1."""
    for regular, bold in _FONT_PAIRS:
        if os.path.exists(regular) and os.path.exists(bold):
            try:
                pdf.add_font("vk", "", regular)
                pdf.add_font("vk", "B", bold)
                return "vk"
            except Exception:  # noqa: S112 — font illeggibile/corrotto: prova il prossimo, poi fallback core
                continue
    return None


# Mappa caratteri non-latin1 verso equivalenti ASCII/latin1 sicuri.
_TRANS = str.maketrans(
    {
        "—": "-",
        "–": "-",
        "•": "-",
        "·": "-",
        "…": "...",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "€": "EUR",
    }
)


def _sanitize(text: str) -> str:
    """Converte i caratteri fuori dal set latin1 in surrogati sicuri."""
    text = text.translate(_TRANS)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _strip_italic(line: str) -> str:
    """Rimuove _..._ wrapping (markdown italic): fpdf2 non lo supporta.
    Lascia invariati **bold** e testo normale."""
    return re.sub(r"(?<![_\*])_([^_]+)_(?![_\*])", r"\1", line)


def _is_heading(line: str) -> bool:
    return line.startswith("#")


def _heading_level(line: str) -> int:
    i = 0
    while i < len(line) and line[i] == "#":
        i += 1
    return i


def recap_md_to_pdf(md: str, out_path: str) -> str:
    """Converte un recap.md in PDF e lo scrive su `out_path`. Ritorna `out_path`.

    Supporta: H1/H2/H3, **bold** inline, righe vuote.
    Non supporta: tabelle, link, italic _..._ (rimossi da _strip_italic).
    """
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(20, 20, 20)
    pdf.add_page()

    # Unicode se un TTF è disponibile, altrimenti core Helvetica + translitterazione latin-1.
    family = _try_unicode_font(pdf)
    unicode_mode = family is not None
    if not unicode_mode:
        family = "Helvetica"
    bullet = "•" if unicode_mode else "-"

    for raw_line in md.splitlines():
        line = raw_line if unicode_mode else _sanitize(raw_line)

        if not line.strip():
            pdf.ln(4)
            continue

        if _is_heading(line):
            level = _heading_level(line)
            text = line.lstrip("#").strip()
            size = max(10, 18 - (level - 1) * 3)
            pdf.set_font(family, style="B", size=size)
            if level == 1:
                pdf.ln(4)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 8, text)
            pdf.set_x(pdf.l_margin)
            pdf.ln(2)
        else:
            stripped = line.lstrip()
            is_bullet = stripped[:2] in ("- ", "* ")
            pdf.set_font(family, size=11)
            if is_bullet:
                # Bullet vero (•) con rientro; il testo conserva **bold** inline.
                body_line = bullet + " " + _strip_italic(stripped[2:])
                pdf.set_x(pdf.l_margin + 4)
            else:
                body_line = _strip_italic(line)
                pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 6, body_line, markdown=True)
            pdf.set_x(pdf.l_margin)

    pdf.output(out_path)
    return out_path
