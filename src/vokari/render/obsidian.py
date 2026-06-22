"""Renderer Analysis -> note Obsidian (spec §8.3) per il second brain.

Genera una nota-sessione (l'ancora) + note atomiche dalle decisioni. Frontmatter
YAML coerente + wikilink `[[...]]`. `export_to_vault` le scrive su disco senza
sovrascrivere (suffisso numerico se il nome esiste già).
"""

import re
from dataclasses import dataclass
from pathlib import Path

from vokari.analyze.schema import Analysis


@dataclass
class ObsidianNote:
    filename: str  # "YYYY-MM-DD – <titolo>.md"
    content: str


_BAD = re.compile(r'[\\/:*?"<>|#\[\]]')


def safe(text: str) -> str:
    """Sanitizza un titolo per usarlo come nome file Obsidian (rimuove i caratteri non
    ammessi, preserva spazi/accenti/maiuscole). API pubblica del modulo."""
    return _BAD.sub("", text).strip() or "Nota"


_safe = safe  # retro-compat per gli usi interni storici


def _short(text: str, n: int = 70) -> str:
    t = " ".join(text.split())
    return t if len(t) <= n else t[:n].rstrip() + "…"


def _frontmatter(d: dict) -> str:
    lines = ["---"]
    for k, v in d.items():
        if isinstance(v, list):
            # YAML block-style: compatibile con Obsidian Dataview
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def render_obsidian_notes(
    analysis: Analysis, *, session_title: str = "", session_date: str = "", da_chiarire: list[str] | None = None
) -> list[ObsidianNote]:
    a = analysis
    date = session_date or a.meta.date or "0000-00-00"
    title = session_title or a.meta.title or "Sessione"
    notes: list[ObsidianNote] = []

    # 1) Nota-sessione (ancora)
    # Salta le entità senza nome: _safe("") → "Nota" genererebbe wikilink [[Nota]] inutili.
    entity_links = [f"[[{_safe(e.name)}]]" for e in a.entities if e.name.strip()]
    body = [
        _frontmatter(
            {
                "title": f'"{title}"',
                "created": date,
                "type": "meeting" if a.meta.type == "meeting" else "permanent",
                "status": "seedling",
                "tags": ["sessione"],
            }
        ),
        "",
        f"# {title}",
        "",
        # Idea centrale = SCOPO (purpose, comprensione-prima); fallback al contesto.
        "**Idea centrale:** " + (a.purpose or a.context or "—"),
        "",
        "## Punti chiave",
        *([f"- {i}" for i in a.key_ideas] or ["- —"]),
    ]
    # Wikilink alle note-decisione atomiche (stesso nome-file generato sotto): l'ancora
    # diventa il punto d'ingresso del secondo cervello verso le decisioni (Zettelkasten).
    dec_links = [
        f"- [[{date} – {_safe(d.title or _short(d.decision))}]]"
        for d in a.decisions
        if d.title.strip() or d.decision.strip()
    ]
    if dec_links:
        body += ["", "## Decisioni", *dec_links]
    if entity_links:
        body += ["", "## Collegamenti", "- " + " · ".join(entity_links)]
    if da_chiarire:
        body += ["", "## Punti da chiarire"]
        body += [f"- ⚠ {punto}" for punto in da_chiarire]
    session_note = ObsidianNote(f"{date} – {_safe(title)}.md", "\n".join(body).rstrip() + "\n")
    notes.append(session_note)

    # 2) Note atomiche dalle decisioni (formato ADR compatto)
    for d in a.decisions:
        # Salta le decisioni completamente vuote: produrrebbero un file "Nota.md" sovrascrivibile
        # e senza contenuto. Basta uno tra title/decision (l'altro fa da fallback nel render).
        if not (d.title.strip() or d.decision.strip()):
            continue
        claim = _safe(d.title or _short(d.decision))
        content = "\n".join(
            [
                _frontmatter(
                    {
                        "title": f'"{d.title or _short(d.decision)}"',
                        "created": date,
                        "type": "decision",
                        "status": "seedling",
                        "source": f'"[[{date} – {_safe(title)}]]"',
                        "tags": ["decisione"],
                    }
                ),
                "",
                f"# {d.title or _short(d.decision)}",
                "",
                "**Decisione:** " + d.decision,
                *(["**Motivazione:** " + d.rationale] if d.rationale else []),
                "",
                f"**Fonte:** [[{date} – {_safe(title)}]]",
            ]
        )
        notes.append(ObsidianNote(f"{date} – {claim}.md", content.rstrip() + "\n"))

    return notes


def export_to_vault(notes: list[ObsidianNote], vault_dir: str | Path) -> list[str]:
    """Scrive le note nel vault (crea la cartella). Non sovrascrive: aggiunge un
    suffisso se il file esiste già. Ritorna i path scritti."""
    vault = Path(vault_dir)
    vault.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for note in notes:
        target = vault / note.filename
        i = 2
        while target.exists():
            target = vault / f"{Path(note.filename).stem} ({i}){Path(note.filename).suffix}"
            i += 1
        target.write_text(note.content, encoding="utf-8")
        written.append(str(target))
    return written
