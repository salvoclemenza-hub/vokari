from pathlib import Path

from vokari.analyze.schema import Analysis, Decision, Entity, Meta, NextStep
from vokari.render import obsidian as obs_mod
from vokari.render import recap as recap_mod


def _analysis() -> Analysis:
    return Analysis(
        meta=Meta(
            type="meeting", title="Riunione Q3", participants=["Marco", "Sara"], duration_min=38, date="2026-06-07"
        ),
        context="Allineamento sulla roadmap del trimestre.",
        key_ideas=["Beta posticipata di due settimane", "Onboarding a tre passi"],
        decisions=[
            Decision(
                title="Beta privata", decision="posticipata di due settimane", rationale="dare tempo all'onboarding"
            )
        ],
        open_questions=["Confermare il fornitore?"],
        next_steps=[NextStep(task="finalizzare copy onboarding", owner="Marco", deadline="2026-06-10")],
        entities=[Entity(name="Marco", type="persona"), Entity(name="Roadmap 2026", type="progetto")],
    )


def test_render_recap_human_readable():
    md = recap_mod.render_recap(_analysis())
    assert md.startswith("# Recap — Riunione Q3")
    assert "## Decisioni" in md
    assert "posticipata di due settimane" in md
    assert "## Prossimi passi" in md and "finalizzare copy onboarding — Marco" in md
    assert "<" not in md  # niente tag XML (consumatore umano)
    assert "raw_transcript" not in md  # niente trascrizione integrale


def test_render_recap_minimal_no_crash():
    md = recap_mod.render_recap(Analysis(meta=Meta()))
    assert "# Recap" in md


def test_recap_leads_with_purpose():
    """R1: 'In breve' guida con lo SCOPO (purpose), il contesto segue come supporto."""
    a = _analysis()
    a.purpose = "Decidere i contenuti della landing page IWA"
    md = recap_mod.render_recap(a)
    assert a.purpose in md
    assert md.index(a.purpose) > md.index("## In breve")
    assert md.index(a.purpose) < md.index(a.context)  # purpose prima, context come supporto


def test_obsidian_idea_centrale_uses_purpose():
    """O1: l'idea centrale della nota-ancora usa il purpose, non il context."""
    a = _analysis()
    a.purpose = "Scopo principale della sessione"
    notes = obs_mod.render_obsidian_notes(a)
    assert "**Idea centrale:** " + a.purpose in notes[0].content


def test_obsidian_anchor_links_decision_notes():
    """O3: la nota-ancora linka le note-decisione atomiche (Zettelkasten / discoverability)."""
    anchor = obs_mod.render_obsidian_notes(_analysis())[0].content
    assert "## Decisioni" in anchor
    assert "[[2026-06-07 – Beta privata]]" in anchor


def test_render_obsidian_skips_empty_entities_and_decisions():
    """Entità/decisioni vuote non devono generare wikilink [[]] né file 'Nota.md' fantasma."""
    a = Analysis(
        meta=Meta(title="X", date="2026-06-10"),
        entities=[Entity(name=""), Entity(name="Marco", type="persona")],
        decisions=[Decision(), Decision(title="Vera", decision="fatto")],
    )
    notes = obs_mod.render_obsidian_notes(a)
    assert len(notes) == 2  # 1 nota-sessione + 1 sola decisione valida
    session = notes[0].content
    assert "[[]]" not in session  # nessun wikilink vuoto
    assert "[[Marco]]" in session  # entità valida conservata


def test_render_obsidian_session_and_decision_notes():
    notes = obs_mod.render_obsidian_notes(_analysis())
    assert len(notes) == 2  # 1 nota-sessione + 1 decisione
    session = notes[0]
    assert session.filename == "2026-06-07 – Riunione Q3.md"
    assert "**Idea centrale:**" in session.content
    assert "[[Marco]]" in session.content
    dec = notes[1]
    assert dec.filename.startswith("2026-06-07 – Beta privata")
    assert "type: decision" in dec.content
    assert "[[2026-06-07 – Riunione Q3]]" in dec.content


def test_export_to_vault_writes_without_overwrite(tmp_path):
    notes = obs_mod.render_obsidian_notes(_analysis())
    written = obs_mod.export_to_vault(notes, tmp_path)
    assert len(written) == 2
    assert all(Path(p).exists() for p in written)
    obs_mod.export_to_vault(notes, tmp_path)  # secondo export: niente overwrite
    assert len(list(tmp_path.glob("*.md"))) == 4


# --- TASK 9: da_chiarire in recap ---


def test_render_recap_includes_da_chiarire_section():
    a = Analysis()
    md = recap_mod.render_recap(a, title="Test", da_chiarire=["Budget beta?", "Fornitore confermato?"])
    assert "## Punti da chiarire" in md
    assert "Budget beta?" in md
    assert "Fornitore confermato?" in md


def test_render_recap_no_da_chiarire_section_when_none():
    a = Analysis()
    md = recap_mod.render_recap(a, title="Test")
    assert "Punti da chiarire" not in md


def test_render_recap_da_chiarire_appears_after_open_questions():
    a = Analysis(open_questions=["Domanda aperta?"])
    md = recap_mod.render_recap(a, title="T", da_chiarire=["Punto irrisolto"])
    pos_oq = md.index("Domande aperte")
    pos_dc = md.index("Punti da chiarire")
    assert pos_dc > pos_oq


# --- TASK 10: da_chiarire + YAML block in obsidian ---


def test_obsidian_notes_include_da_chiarire_in_session_note():
    a = Analysis()
    notes = obs_mod.render_obsidian_notes(a, session_title="Test", da_chiarire=["Budget non confermato"])
    session_note = notes[0].content
    assert "Punti da chiarire" in session_note
    assert "Budget non confermato" in session_note


def test_obsidian_frontmatter_uses_yaml_block_for_lists():
    a = Analysis()
    notes = obs_mod.render_obsidian_notes(a, session_title="T", session_date="2026-06-11")
    content = notes[0].content
    # YAML block: tags:\n  - sessione (non tags: [sessione])
    assert "tags:\n  - sessione" in content, f"frontmatter deve usare YAML block per tags, trovato: {content[:300]}"
