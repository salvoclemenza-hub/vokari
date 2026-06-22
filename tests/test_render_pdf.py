"""Test per vokari.render.pdf — genera un PDF da un recap.md.

Seam reale: il file esiste su disco con dimensione > 0.
Copre: testo con accenti italiani, trattini lunghi e caratteri speciali che
rompevano gli encoding latin1 di fpdf2 (ADR M7/H).
"""

from pathlib import Path


def test_recap_md_to_pdf_crea_file(tmp_path: Path):
    from vokari.render.pdf import recap_md_to_pdf

    md = "# Recap - Test\n\nUna nota con accenti: a e i o u.\n- trattino lungo: -\n"
    out = str(tmp_path / "test.pdf")
    result = recap_md_to_pdf(md, out)
    assert result == out
    assert Path(out).exists()
    assert Path(out).stat().st_size > 0


def test_recap_md_to_pdf_non_solleva_con_caratteri_speciali(tmp_path: Path):
    """Caratteri non-latin1 frequenti nell'italiano non devono sollevare UnicodeEncodeError."""
    from vokari.render.pdf import recap_md_to_pdf

    # em-dash, smart quotes, ellipsis, bullet, euro sign — tutti rischiosi con latin1
    md = (
        "# Riunione – Q3\n\n"
        "Partecipanti: Marco, Béatrice.\n"
        "Virgolette tipografiche: “testo” e ‘altro’.\n"
        "Puntini: …e poi niente.\n"
        "Bullet • punto • centrale.\n"
        "Euro: €120.\n"
    )
    out = str(tmp_path / "special.pdf")
    recap_md_to_pdf(md, out)  # non deve sollevare
    assert Path(out).stat().st_size > 0


def test_recap_md_to_pdf_md_vuoto(tmp_path: Path):
    """Un md vuoto produce comunque un PDF valido (> 0 byte)."""
    from vokari.render.pdf import recap_md_to_pdf

    out = str(tmp_path / "empty.pdf")
    recap_md_to_pdf("", out)
    assert Path(out).exists()
    assert Path(out).stat().st_size > 0


def test_strip_italic_removes_underscore_markers():
    from vokari.render.pdf import _strip_italic

    assert _strip_italic("_data e ora_") == "data e ora"
    assert _strip_italic("testo normale") == "testo normale"
    # bold non viene toccato da _strip_italic
    result = _strip_italic("**bold** rimane")
    assert "bold" in result


def test_pdf_renders_without_error_with_bold_markdown(tmp_path):
    """PDF generato senza errori su recap con **bold**."""
    import os

    from vokari.render.pdf import recap_md_to_pdf

    md = "# Recap - Test\n\n## Decisioni\n\n- **Rinvio beta** - Posticipata\n"
    out = str(tmp_path / "test.pdf")
    recap_md_to_pdf(md, out)
    assert os.path.exists(out)
    assert os.path.getsize(out) > 0


def test_pdf_renders_italic_metadata_line(tmp_path):
    """Riga _data - durata_ non causa errori nel PDF."""
    import os

    from vokari.render.pdf import recap_md_to_pdf

    md = "# Recap\n\n_2026-06-11 - 30 min_\n\n## In breve\ntesto\n"
    out = str(tmp_path / "italic.pdf")
    recap_md_to_pdf(md, out)
    assert os.path.exists(out) and os.path.getsize(out) > 0
