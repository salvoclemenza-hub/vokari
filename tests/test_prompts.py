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


def test_build_user_contains_fewshot_generic():
    """Il prompt utente include un esempio few-shot generico (nessun dominio aziendale)
    con tutti i campi JSON popolati per stabilizzare la granularità su Ollama."""
    from vokari.analyze.prompts import build_user

    prompt = build_user("qualsiasi trascrizione", mode="riunione")
    # Il few-shot è presente e usa esempio generico (newsletter/Sara)
    assert "Sara" in prompt, "Esempio few-shot deve contenere il marker generico 'Sara'"
    assert "newsletter" in prompt, "Esempio few-shot deve contenere 'newsletter'"
    # Tutti i campi strutturali devono essere presenti nel few-shot
    assert '"decisions"' in prompt, "Esempio few-shot deve mostrare il campo 'decisions'"
    assert '"next_steps"' in prompt, "Esempio few-shot deve mostrare il campo 'next_steps'"
    assert '"entities"' in prompt, "Esempio few-shot deve mostrare il campo 'entities'"
    assert '"purpose"' in prompt, "Esempio few-shot deve mostrare il campo 'purpose'"


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


# --- Test per build_verify_user (struttura PASSO 1/2/3, ADR comprensione-prima) ----


def _make_analysis():
    from vokari.analyze.schema import Analysis

    return Analysis(purpose="scopo sbagliato", context="ctx")


def test_verify_user_has_passo_steps():
    """Il verify prompt ha i 3 passi espliciti per lettura indipendente prima del confronto."""
    v = prompts.build_verify_user("trascrizione test", _make_analysis(), mode="riunione")
    assert "PASSO 1" in v
    assert "PASSO 2" in v
    assert "PASSO 3" in v


def test_verify_user_independent_first():
    """PASSO 1 invita a individuare il punto INDIPENDENTEMENTE (senza guardare l'analisi)."""
    v = prompts.build_verify_user("trascrizione test", _make_analysis(), mode="riunione")
    assert "INDIPENDENTEMENTE" in v


def test_verify_user_transcript_before_analysis():
    """TRASCRIZIONE deve comparire PRIMA della sezione ANALISI CORRENTE nel testo del prompt
    (forza la lettura indipendente prima di vedere la potenziale analisi sbagliata).
    Nota: 'ANALISI CORRENTE' compare anche all'interno di PASSO 2 come citazione — il marcatore
    usato qui è l'intestazione di sezione, che è più specifica e unica nel prompt."""
    v = prompts.build_verify_user("TESTO_UNICO_123", _make_analysis(), mode="riunione")
    pos_transcript = v.index("TESTO_UNICO_123")
    # Usa l'intestazione di sezione completa (non la menzione in PASSO 2)
    section_header = "ANALISI CORRENTE (confronta"
    pos_analysis_section = v.index(section_header)
    assert pos_transcript < pos_analysis_section, (
        "Il testo della TRASCRIZIONE deve apparire prima della sezione ANALISI CORRENTE"
    )


def test_verify_user_mezzo_vs_fine_hint():
    """Il verify prompt include il concetto MEZZO vs FINE per guidare la discriminazione."""
    v = prompts.build_verify_user("t", _make_analysis(), mode="riunione")
    assert "MEZZO" in v and "FINE" in v


def test_verify_user_injects_context():
    """Se context è fornito, viene iniettato nel verify prompt."""
    v = prompts.build_verify_user("t", _make_analysis(), mode="riunione", context="landing page Kamil")
    assert "landing page Kamil" in v


def test_verify_user_contains_full_analysis_json():
    """Il verify prompt include l'Analysis JSON completo (per confronto con PASSO 2)."""
    a = _make_analysis()
    v = prompts.build_verify_user("t", a, mode="riunione")
    assert a.model_dump_json() in v
