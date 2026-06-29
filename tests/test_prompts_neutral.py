from vokari import i18n
from vokari.analyze import prompts

_FORBIDDEN = ["magazzino aliment", "food warehouse", "VMM", "HACCP", "DDT", "acciughe", "miscelazione"]


def test_system_prompt_is_domain_neutral():
    sys_it = prompts.build_system("it").lower()
    sys_en = prompts.build_system("en").lower()
    for term in _FORBIDDEN:
        assert term.lower() not in sys_it, f"termine di dominio nel system IT: {term}"
        assert term.lower() not in sys_en, f"termine di dominio nel system EN: {term}"


def test_fewshot_is_generic_but_complete():
    # il few-shot deve restare presente (stabilizza il JSON su Ollama) ma senza gergo aziendale,
    # e mostrare tutti i campi popolati.
    fs = prompts._FEWSHOT
    low = fs.lower()
    for term in _FORBIDDEN:
        assert term.lower() not in low, f"termine di dominio nel few-shot: {term}"
    for field in ['"purpose"', '"decisions"', '"open_questions"', '"next_steps"', '"entities"', '"key_ideas"']:
        assert field in fs, f"campo mancante nel few-shot: {field}"


def test_fewshot_single_example_with_markers():
    """Il few-shot contiene esattamente UN esempio (newsletter/Sara) con tutti i campi.
    Un secondo esempio 'buried-decision' era stato testato (eval v4) ma causava
    cross-contamination su qwen2.5:7b: il modello copiava surface-feature dell'esempio
    (es. open_question sull'invito) invece di imparare il pattern MEZZO/FINE. Revertito."""
    fs = prompts._FEWSHOT
    # Marker del singolo esempio: newsletter + Sara
    assert "Sara" in fs, "Esempio few-shot usa il marker generico 'Sara'"
    assert "newsletter" in fs, "Esempio few-shot usa 'newsletter' come dominio generico"
    # NON deve esserci un secondo esempio esplicito
    assert "Esempio 2" not in fs, "Non deve esserci un secondo esempio (cross-contamination)"


def test_briefing_instructions_are_domain_neutral():
    for key in ("briefing.instr_meeting", "briefing.instr_solo"):
        for lang in ("it", "en"):
            txt = i18n.t(key, lang).lower()
            for term in ("magazzino aliment", "food warehouse", "vmm", "haccp", "mac processing"):
                assert term not in txt, f"{key}/{lang} contiene dominio: {term}"


def test_user_context_injected_when_present():
    ctx = "Magazzino alimentare B2B: lotti VMM, MAC, HACCP"
    sys_with = prompts.build_system("it", user_context=ctx)
    assert "VMM" in sys_with and ctx in sys_with
    sys_without = prompts.build_system("it", user_context="")
    assert "VMM" not in sys_without


def test_user_context_truncated_to_reasonable_budget():
    long_ctx = "x" * 600
    short_ctx = "y" * 200
    # Tronca contesti lunghi: la stringa originale intera NON deve comparire, ma viene aggiunto "..."
    sys_long = prompts.build_system("it", user_context=long_ctx)
    assert "..." in sys_long
    assert long_ctx not in sys_long  # il testo originale integrale è assente (troncato)
    # Preserva contesti brevi
    sys_short = prompts.build_system("it", user_context=short_ctx)
    assert short_ctx in sys_short
