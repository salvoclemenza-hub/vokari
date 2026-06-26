from vokari.analyze import prompts


def test_system_demands_json_only():
    s = prompts.build_system()
    assert "JSON" in s
    assert "code fence" in s.lower() or "markdown" in s.lower()


def test_user_includes_transcript_and_shape():
    u = prompts.build_user("ciao mondo", mode="solo")
    assert "ciao mondo" in u
    # menziona le chiavi dello schema §7
    for key in ("meta", "key_ideas", "decisions", "open_questions", "next_steps", "entities"):
        assert key in u


def test_user_meeting_vs_solo_differ():
    assert prompts.build_user("t", mode="meeting") != prompts.build_user("t", mode="solo")


def test_user_riunione_maps_to_meeting_focus():
    # 'riunione' (valore canonico UI/settings) deve usare il focus 'meeting', non il fallback 'solo'.
    assert prompts.build_user("t", mode="riunione") == prompts.build_user("t", mode="meeting")
    assert prompts.build_user("t", mode="riunione") != prompts.build_user("t", mode="solo")


def test_user_injects_refinement_answers():
    u = prompts.build_user("t", mode="solo", refinement={"Budget?": "10k"})
    assert "Budget?" in u and "10k" in u


def test_user_injects_known_meta():
    u = prompts.build_user("t", mode="meeting", meta={"title": "Roadmap Q3", "participants": ["Ada"]})
    assert "Roadmap Q3" in u and "Ada" in u


def test_build_user_contains_fewshot_with_vmm_terminology():
    """Il prompt utente include un esempio con terminologia VMM/MAC/HACCP."""
    from vokari.analyze.prompts import build_user

    prompt = build_user("qualsiasi trascrizione", mode="riunione")
    assert "VMM" in prompt, "Esempio few-shot deve contenere terminologia VMM"
    assert "MAC" in prompt, "Esempio few-shot deve contenere terminologia MAC"
    assert "HACCP" in prompt, "Esempio few-shot deve contenere terminologia HACCP"


def test_build_user_fewshot_shows_expected_json_structure():
    """Il few-shot mostra la struttura JSON attesa."""
    from vokari.analyze.prompts import build_user

    prompt = build_user("trascrizione", mode="solo")
    assert '"decisions"' in prompt
    assert '"next_steps"' in prompt
    assert '"entities"' in prompt


def test_build_user_includes_context():
    """Se fornito, context viene iniettato con etichetta CONTESTO."""
    u = prompts.build_user("t", mode="riunione", context="decidere landing page")
    assert "decidere landing page" in u
    assert "CONTESTO" in u.upper()  # etichetta visibile


def test_analysis_has_purpose_field():
    """Analysis ha un campo `purpose` (lo scopo/punto principale in 1-2 frasi), default vuoto."""
    from vokari.analyze.schema import Analysis

    assert Analysis().purpose == ""
    assert Analysis(purpose="Decidere la landing page B2B").purpose == "Decidere la landing page B2B"


def test_build_user_asks_for_purpose_first():
    """Il prompt chiede di individuare lo SCOPO (campo purpose) come prima cosa."""
    u = prompts.build_user("t", mode="riunione")
    assert "purpose" in u  # il campo purpose è nella shape JSON
    assert "SCOPO" in u.upper()  # istruzione esplicita a individuare lo scopo


def test_user_injects_markers():
    u = prompts.build_user("t", mode="solo", markers=[{"t_ms": 90_000, "label": "Lotto X"}])
    assert "SEGNALIBRI" in u.upper()
    assert "Lotto X" in u
    assert "01:30" in u  # 90 s formattato


def test_user_no_markers_block_when_empty():
    u = prompts.build_user("t", mode="solo")
    assert "SEGNALIBRI" not in u.upper()
