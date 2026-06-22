from vokari.store.session import Session


def test_new_generates_id_and_timestamp():
    s = Session.new(title="Test", mode="solo", source="mic")
    assert s.id and isinstance(s.id, str)
    assert s.created_at.endswith("Z") or "T" in s.created_at  # ISO 8601
    assert s.title == "Test"
    assert s.status == "idle"
    assert s.markers == []


def test_defaults_match_spec():
    s = Session.new()
    assert s.title == "Sessione senza titolo"
    assert s.mode == "solo"
    assert s.language == "auto"


def test_to_dict_from_dict_roundtrip():
    s = Session.new(title="Riunione", mode="riunione", source="both")
    s.transcript = "ciao mondo"
    s.word_count = 2
    d = s.to_dict()
    s2 = Session.from_dict(d)
    assert s2 == s


def test_from_dict_ignores_unknown_keys():
    s = Session.new()
    d = s.to_dict()
    d["_legacy"] = 123
    s2 = Session.from_dict(d)
    assert s2.id == s.id


def test_from_transcript_result_populates_fields():
    result = {
        "text": "ciao mondo come va",
        "model": "large-v3-turbo",
        "language": "it",
        "source": "rec.m4a",
        "duration_s": 120.0,
    }
    s = Session.from_transcript_result(result, mode="solo")
    assert s.transcript == "ciao mondo come va"
    assert s.model == "large-v3-turbo"
    assert s.language == "it"
    assert s.audio_path == "rec.m4a"
    assert s.duration_ms == 120000
    assert s.word_count == 4
    assert s.status == "transcribed" if hasattr(s, "status") else True
