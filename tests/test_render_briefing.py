from vokari.analyze.schema import Analysis, NextStep
from vokari.render import briefing


def _sample() -> Analysis:
    return Analysis.model_validate(
        {
            "meta": {
                "type": "meeting",
                "title": "Roadmap Q3",
                "participants": ["Ada", "Bob"],
                "duration_min": 38,
                "date": "2026-06-07",
            },
            "context": "Allineamento sulla roadmap.",
            "key_ideas": ["Beta privata", "Onboarding a 3 step"],
            "decisions": [
                {"title": "Rinvio beta", "decision": "Posticipata 2 settimane", "rationale": "Rifinire onboarding"}
            ],
            "open_questions": ["Budget beta confermato?", "Destinatario del briefing?"],
            "next_steps": [
                {"task": "Copy onboarding", "owner": "Marco", "deadline": None},
                {"task": "Test offline", "owner": "Sara", "deadline": "2026-06-20"},
            ],
            "entities": [{"name": "Beta", "type": "progetto", "note": "lancio privato"}],
        }
    )


def test_briefing_has_frontmatter_and_xml_sections():
    md = briefing.render_briefing(
        _sample(),
        source="rec.m4a",
        transcription_model="large-v3-turbo",
        llm_model="claude-opus-4-8",
        transcript="testo integrale",
    )
    assert md.startswith("---\n")
    assert "type: meeting" in md
    assert "source: rec.m4a" in md
    assert "transcription_model: large-v3-turbo" in md
    assert "<context>" in md and "</context>" in md
    assert "<decisions>" in md
    assert "<raw_transcript>" in md and "testo integrale" in md


def test_briefing_shows_purpose_near_top():
    """Il purpose (scopo) compare in cima al briefing, prima di contesto e decisioni."""
    a = _sample()
    a.purpose = "Decidere se realizzare la landing page B2B e cosa metterci"
    md = briefing.render_briefing(a, transcript="t")
    assert a.purpose in md
    assert "<purpose>" in md
    assert md.index(a.purpose) < md.index("## Contesto")
    assert md.index(a.purpose) < md.index("Decisioni prese")


def test_briefing_omits_purpose_block_when_empty():
    """Analisi pre-purpose (campo vuoto): nessun blocco <purpose> vuoto (retro-compatibilità)."""
    md = briefing.render_briefing(_sample(), transcript="t")  # _sample() ha purpose default ""
    assert "<purpose>" not in md


def test_open_questions_appear_once():
    """B2: rimossa la doppia stampa (la 'ripetizione in coda' recency confondeva e sembrava un bug)."""
    md = briefing.render_briefing(_sample(), transcript="t")
    assert md.count("Budget beta confermato?") == 1
    assert "ripetizione in coda" not in md


def test_da_chiarire_markers_render():
    md = briefing.render_briefing(_sample(), transcript="t", da_chiarire=["Budget non confermato in rifinitura"])
    assert "[DA CHIARIRE: Budget non confermato in rifinitura]" in md


def test_frontmatter_quotes_yaml_unsafe_strings():
    a = _sample()
    a.meta.participants = ["Dott: Rossi", "Bob"]
    a.meta.title = "Riunione: Q3"
    md = briefing.render_briefing(a, transcript="t")
    # participants e topic con ':' devono restare YAML validi (quotati)
    assert '"Dott: Rossi"' in md
    assert 'topic: "Riunione: Q3"' in md


def test_next_steps_render_as_checklist_with_owner():
    md = briefing.render_briefing(_sample(), transcript="t")
    assert "- [ ]" in md
    assert "Marco" in md and "Copy onboarding" in md


def test_next_steps_skip_empty_task():
    a = _sample()
    a.next_steps = [
        NextStep(task="Copy onboarding", owner="Marco"),
        NextStep(task="   ", owner="Sara"),
    ]
    md = briefing.render_briefing(a, transcript="t")
    assert "- [ ] Copy onboarding — Marco" in md
    # nessuna riga checkbox col task vuoto/whitespace (eventuale owner orfano incluso)
    for line in md.splitlines():
        if line.startswith("- [ ] "):
            body = line[len("- [ ] ") :]
            # il testo prima di un eventuale " — owner" non deve essere vuoto
            task_part = body.split(" — ", 1)[0]
            assert task_part.strip() != "", f"checkbox con task vuoto: {line!r}"


def test_next_steps_all_empty_falls_back_to_placeholder():
    a = _sample()
    a.next_steps = [
        NextStep(task="", owner=None),
        NextStep(task="  ", owner="Sara"),
    ]
    md = briefing.render_briefing(a, transcript="t")
    assert "- [ ] (nessun prossimo passo)" in md


def test_frontmatter_includes_language_when_provided():
    from vokari.analyze.schema import Analysis

    a = Analysis()
    md = briefing.render_briefing(a, source="rec.m4a", language="it")
    assert "language: it" in md


def test_frontmatter_includes_word_count_when_provided():
    from vokari.analyze.schema import Analysis

    a = Analysis()
    md = briefing.render_briefing(a, source="rec.m4a", word_count=42)
    assert "word_count: 42" in md


def test_frontmatter_omits_language_when_not_provided():
    from vokari.analyze.schema import Analysis

    a = Analysis()
    md = briefing.render_briefing(a)
    assert "language:" not in md


def test_session_instruction_mentions_domain_terminology():
    from vokari.analyze.schema import Analysis

    a = Analysis()
    md = briefing.render_briefing(a)
    domain_terms = ["HACCP", "VMM", "tracciabilità", "MAC"]
    found = [t for t in domain_terms if t in md]
    assert found, f"session_instruction deve citare il dominio alimentare, cercati: {domain_terms}"


def test_session_instruction_differs_by_meta_type():
    import re

    from vokari.analyze.schema import Analysis, Meta

    a_meeting = Analysis(meta=Meta(type="meeting"))
    a_solo = Analysis(meta=Meta(type="solo"))
    md_meeting = briefing.render_briefing(a_meeting)
    md_solo = briefing.render_briefing(a_solo)

    def _extract_instruction(md):
        m = re.search(r"<session_instruction>(.*?)</session_instruction>", md, re.DOTALL)
        return m.group(1).strip() if m else ""

    assert _extract_instruction(md_meeting) != _extract_instruction(md_solo)


def test_briefing_renders_user_markers_section():
    md = briefing.render_briefing(
        _sample(),
        transcript="t",
        markers=[{"t_ms": 90_000, "label": "Decisione lotto"}, {"t_ms": 5_000, "label": "Intro"}],
    )
    assert "<user_markers>" in md and "</user_markers>" in md
    assert "Segnalibri" in md
    assert "- 00:05 — Intro" in md  # ordinati per tempo
    assert "- 01:30 — Decisione lotto" in md
    # i segnalibri precedono la trascrizione integrale (sono puntatori nell'audio)
    assert md.index("<user_markers>") < md.index("<raw_transcript>")


def test_briefing_no_markers_section_when_none():
    md = briefing.render_briefing(_sample(), transcript="t")
    assert "<user_markers>" not in md
