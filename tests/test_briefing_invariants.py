"""Livello 1 eval strutturale: invarianti del briefing.md su transcript fisso.

Questi test non usano un LLM reale. Verificano che:
1. Il template produce la struttura XML attesa su qualsiasi Analysis valida.
2. I campi critici (frontmatter, sezioni, word_count, language) sono presenti.
3. Le regressioni del template vengono rilevate prima del commit.

Per Livello 2 (golden output con LLM reale) vedi test_briefing_golden.py (da creare).
"""

from pathlib import Path

from vokari.analyze.schema import Analysis, Decision, Entity, Meta, NextStep
from vokari.render.briefing import render_briefing

_FIXTURES = Path(__file__).parent / "fixtures"

# Analysis "realistica" con terminologia aziendale — simula output LLM su trascrizione VMM
_REALISTIC_ANALYSIS = Analysis(
    meta=Meta(type="meeting", title="Lotto VMM-2026-9999", participants=["Mario"], duration_min=20, date="2026-06-11"),
    context="Riunione operativa per verifica resa lotto VMM-2026-9999 (acciughe, MAC).",
    key_ideas=["Resa MAC 90% — entro soglia", "Lotto rilasciato per distribuzione"],
    decisions=[
        Decision(
            title="Rilascio lotto VMM-2026-9999",
            decision="Lotto approvato per distribuzione",
            rationale="Resa MAC 90% supera soglia minima 85%",
        )
    ],
    open_questions=["Il fornitore Rossi ha confermato la prossima consegna?"],
    next_steps=[NextStep(task="Aggiornare registro HACCP", owner="Mario", deadline="2026-06-14")],
    entities=[
        Entity(name="VMM-2026-9999", type="termine", note="lotto rilasciato"),
        Entity(name="Mario", type="persona", note="responsabile HACCP"),
    ],
)


class TestBriefingStructure:
    """Invarianti strutturali: ogni briefing deve averle, sempre."""

    def test_has_yaml_frontmatter(self):
        md = render_briefing(_REALISTIC_ANALYSIS)
        assert md.startswith("---\n"), "Il briefing deve iniziare con frontmatter YAML"
        assert "\n---\n" in md[3:], "Il frontmatter YAML deve essere chiuso da ---"

    def test_frontmatter_has_required_fields(self):
        md = render_briefing(
            _REALISTIC_ANALYSIS,
            source="test.m4a",
            language="it",
            word_count=50,
            llm_model="claude-sonnet-4-6",
            transcription_model="large-v3-turbo",
            session_id="s-001",
        )
        assert "type:" in md
        assert "language: it" in md
        assert "word_count: 50" in md
        assert "llm_model:" in md
        assert "transcription_model:" in md
        assert "session_id: s-001" in md

    def test_has_all_xml_sections(self):
        md = render_briefing(_REALISTIC_ANALYSIS)
        for tag in [
            "session_instruction",
            "context",
            "decisions",
            "session_summary",
            "open_questions",
            "raw_transcript",
        ]:
            assert f"<{tag}>" in md, f"Sezione XML <{tag}> mancante nel briefing"
            assert f"</{tag}>" in md, f"Chiusura XML </{tag}> mancante nel briefing"

    def test_session_instruction_mentions_domain(self):
        md = render_briefing(_REALISTIC_ANALYSIS)
        domain_terms = ["HACCP", "VMM", "tracciabilità", "MAC"]
        found = [t for t in domain_terms if t in md]
        assert found, f"session_instruction deve citare il dominio alimentare. Cercati: {domain_terms}"

    def test_open_questions_appear_once(self):
        # B2 (ADR-039): rimossa la ripetizione in coda (recency) — confondeva e sembrava un bug.
        md = render_briefing(_REALISTIC_ANALYSIS)
        count = md.count("Domande aperte")
        assert count == 1, f"open_questions deve apparire 1 volta (no doppione), trovato {count}"

    def test_next_steps_are_checkboxes(self):
        md = render_briefing(_REALISTIC_ANALYSIS)
        assert "- [ ]" in md, "I next_steps devono essere checkbox Markdown"

    def test_raw_transcript_section_contains_transcript(self):
        transcript = "testo di test della trascrizione"
        md = render_briefing(_REALISTIC_ANALYSIS, transcript=transcript)
        assert transcript in md, "La trascrizione integrale deve essere nel briefing"

    def test_no_xml_sections_empty(self):
        """Nessuna sezione XML deve essere vuota con un'Analysis popolata."""
        md = render_briefing(_REALISTIC_ANALYSIS)
        import re

        for tag in ["context", "decisions", "session_summary"]:
            m = re.search(rf"<{tag}>(.*?)</{tag}>", md, re.DOTALL)
            assert m, f"Sezione <{tag}> non trovata"
            content = m.group(1).strip()
            assert content and "(non disponibile)" not in content, f"Sezione <{tag}> è vuota con Analysis popolata"


class TestBriefingDaChiarire:
    def test_da_chiarire_markers_appear_in_briefing(self):
        markers = ["Budget non confermato", "Fornitore sconosciuto"]
        md = render_briefing(_REALISTIC_ANALYSIS, da_chiarire=markers)
        assert "[DA CHIARIRE: Budget non confermato]" in md
        assert "[DA CHIARIRE: Fornitore sconosciuto]" in md

    def test_no_da_chiarire_markers_when_empty(self):
        md = render_briefing(_REALISTIC_ANALYSIS, da_chiarire=[])
        assert "[DA CHIARIRE:" not in md

    def test_da_chiarire_does_not_appear_when_none(self):
        md = render_briefing(_REALISTIC_ANALYSIS)
        assert "[DA CHIARIRE:" not in md


class TestBriefingDomainTerminology:
    """Verifica che l'Analysis con dati VMM produca output che li include."""

    def test_vmm_lotto_appears_in_briefing(self):
        md = render_briefing(_REALISTIC_ANALYSIS)
        assert "VMM-2026-9999" in md

    def test_participant_mario_appears_in_briefing(self):
        md = render_briefing(_REALISTIC_ANALYSIS)
        assert "Mario" in md


class TestBriefingRecapObsidianConsistency:
    """I 3 artefatti da un'unica Analysis sono coerenti tra loro."""

    def test_title_consistent_across_artefacts(self):
        from vokari.render.obsidian import render_obsidian_notes
        from vokari.render.recap import render_recap

        title = _REALISTIC_ANALYSIS.meta.title
        briefing = render_briefing(_REALISTIC_ANALYSIS)
        recap = render_recap(_REALISTIC_ANALYSIS)
        obsidian = render_obsidian_notes(_REALISTIC_ANALYSIS)[0].content
        assert title in briefing
        assert title in recap
        assert title in obsidian

    def test_da_chiarire_propagates_to_recap_and_obsidian(self):
        from vokari.render.obsidian import render_obsidian_notes
        from vokari.render.recap import render_recap

        markers = ["Punto irrisolto critico"]
        briefing = render_briefing(_REALISTIC_ANALYSIS, da_chiarire=markers)
        recap = render_recap(_REALISTIC_ANALYSIS, da_chiarire=markers)
        obsidian = render_obsidian_notes(_REALISTIC_ANALYSIS, da_chiarire=markers)[0].content
        assert "Punto irrisolto critico" in briefing
        assert "Punto irrisolto critico" in recap
        assert "Punto irrisolto critico" in obsidian
