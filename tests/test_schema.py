from vokari.analyze.schema import Analysis, Entity, Meta


def test_analysis_minimal_valid():
    a = Analysis(meta=Meta(type="solo"))
    assert a.meta.type == "solo"
    assert a.key_ideas == [] and a.decisions == [] and a.next_steps == []


def test_analysis_from_full_dict():
    raw = {
        "meta": {
            "type": "meeting",
            "title": "Q3",
            "participants": ["Ada", "Bob"],
            "duration_min": 47,
            "date": "2026-06-07",
        },
        "context": "Allineamento roadmap.",
        "key_ideas": ["Beta privata", "Onboarding a 3 step"],
        "decisions": [
            {"title": "Rinvio beta", "decision": "Posticipata 2 settimane", "rationale": "Rifinire onboarding"}
        ],
        "open_questions": ["Budget beta confermato?"],
        "next_steps": [{"task": "Copy onboarding", "owner": "Marco", "deadline": None}],
        "entities": [{"name": "Beta", "type": "progetto", "note": "lancio privato"}],
    }
    a = Analysis.model_validate(raw)
    assert a.meta.participants == ["Ada", "Bob"]
    assert a.decisions[0].decision == "Posticipata 2 settimane"
    assert a.next_steps[0].owner == "Marco" and a.next_steps[0].deadline is None


def test_analysis_tolerates_missing_optional_fields():
    a = Analysis.model_validate({"meta": {"type": "solo"}, "context": "x"})
    assert a.entities == [] and a.open_questions == []


def test_analysis_bare_constructor_is_valid():
    """Analysis() senza argomenti NON deve sollevare ValidationError: meta ha un default
    (usato nei rami fallback, es. export_obsidian senza analysis)."""
    a = Analysis()
    assert a.meta.type == "solo" and a.meta.title == ""
    assert a.key_ideas == [] and a.decisions == []


def test_entity_type_coerces_unknown_to_termine():
    """Bug 2026-06-30: l'LLM può restituire tipi entità fuori dall'enum (es. 'evento').
    NON deve far fallire l'Analysis (si perderebbe il briefing): i tipi sconosciuti si
    bucketizzano sul fallback 'termine'."""
    assert Entity(name="Sagra", type="evento").type == "termine"
    assert Entity(name="Acme", type="azienda").type == "termine"
    assert Entity(name="Milano", type="luogo").type == "termine"


def test_meta_type_coerces_unknown_to_solo():
    assert Meta(type="workshop").type == "solo"


def test_entity_and_meta_type_map_known_synonyms():
    # Sinonimi (anche EN, quando l'output AI è in altra lingua) → canonico IT.
    assert Entity(name="Ada", type="person").type == "persona"
    assert Entity(name="Beta", type="Project").type == "progetto"
    assert Meta(type="riunione").type == "meeting"


def test_analysis_with_unknown_entity_type_does_not_raise():
    """Regressione esatta del crash riportato (entities[1].type='evento' → literal_error
    bloccava l'INTERA Analysis): ora l'analisi passa e il tipo fuori-lista è 'termine'."""
    raw = {
        "meta": {"type": "meeting"},
        "entities": [
            {"name": "Sara", "type": "persona", "note": ""},
            {"name": "Sagra di paese", "type": "evento", "note": "data da fissare"},
        ],
    }
    a = Analysis.model_validate(raw)
    assert [e.type for e in a.entities] == ["persona", "termine"]


def test_entity_type_accepts_valid_values():
    for t in ("persona", "progetto", "termine"):
        e = Entity(name="X", type=t)
        assert e.type == t


def test_meta_type_accepts_valid_values():
    for t in ("meeting", "solo"):
        m = Meta(type=t)
        assert m.type == t
