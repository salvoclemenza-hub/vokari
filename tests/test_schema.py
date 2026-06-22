import pytest

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


def test_entity_type_rejects_invalid_value():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Entity(name="Acme", type="azienda")  # non in Literal


def test_meta_type_rejects_invalid_value():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Meta(type="workshop")  # non in Literal


def test_entity_type_accepts_valid_values():
    for t in ("persona", "progetto", "termine"):
        e = Entity(name="X", type=t)
        assert e.type == t


def test_meta_type_accepts_valid_values():
    for t in ("meeting", "solo"):
        m = Meta(type=t)
        assert m.type == t
