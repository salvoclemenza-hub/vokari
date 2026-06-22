from vokari.analyze import interview as IV
from vokari.analyze.schema import Analysis, Meta


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def chat_json(self, system, user):
        self.calls.append((system, user))
        return self.payload

    def chat_text(self, system, user):
        return ""


def _analysis():
    return Analysis(meta=Meta(type="solo", title="X"), context="parlavamo di pricing")


def test_detect_questions_validates_caps_and_sorts_by_priority():
    payload = {
        "questions": [
            {"id": "q1", "text": "Qual e il budget?", "priority": "low", "suggestions": ["10k", "20k"]},
            {"id": "q2", "text": "Chi e il destinatario?", "priority": "high"},
            {"id": "q3", "text": "Entro quando?", "priority": "medium"},
            {"id": "q4", "text": "D4", "priority": "high"},
            {"id": "q5", "text": "D5", "priority": "low"},
            {"id": "q6", "text": "D6", "priority": "low"},
        ]
    }
    prov = FakeProvider(payload)
    qs = IV.detect_questions(_analysis(), "trascrizione", provider=prov, mode="solo")
    assert len(qs) == 5
    assert [q.priority for q in qs[:2]] == ["high", "high"]
    assert qs[0].id in {"q2", "q4"}
    assert prov.calls, "deve interrogare il provider"


def test_detect_questions_dedups_against_open_questions():
    """D1: non richiede a voce ciò che l'analisi marca già come domanda aperta."""
    a = Analysis(meta=Meta(type="solo", title="X"), open_questions=["Qual è il budget?"])
    payload = {
        "questions": [
            {"id": "q1", "text": "Qual è il budget?", "priority": "high"},  # già aperta → scartata
            {"id": "q2", "text": "Chi è il destinatario?", "priority": "high"},
        ]
    }
    qs = IV.detect_questions(a, "t", provider=FakeProvider(payload), mode="solo")
    texts = [q.text for q in qs]
    assert "Chi è il destinatario?" in texts
    assert "Qual è il budget?" not in texts


def test_detect_questions_parses_why_and_from_audio():
    """I1+I2: why e fromAudio vengono letti dal JSON dell'LLM (alias fromAudio→from_audio)."""
    payload = {
        "questions": [
            {
                "id": "q1",
                "text": "Budget 700 o 730?",
                "priority": "high",
                "why": "valori in contraddizione",
                "fromAudio": True,
            },
        ]
    }
    qs = IV.detect_questions(_analysis(), "t", provider=FakeProvider(payload), mode="solo")
    assert qs[0].why == "valori in contraddizione"
    assert qs[0].from_audio is True


def test_detect_questions_accepts_snake_from_audio():
    """Robustezza: l'LLM può emettere from_audio (snake) invece di fromAudio (alias) — entrambi ok."""
    payload = {"questions": [{"id": "q1", "text": "Domanda?", "priority": "high", "from_audio": True}]}
    qs = IV.detect_questions(_analysis(), "t", provider=FakeProvider(payload), mode="solo")
    assert qs[0].from_audio is True


def test_detect_questions_why_from_audio_optional_default():
    """Retro-compat: se l'LLM non popola why/fromAudio, default vuoti — degrada, non rompe."""
    payload = {"questions": [{"id": "q1", "text": "Domanda?", "priority": "high"}]}
    qs = IV.detect_questions(_analysis(), "t", provider=FakeProvider(payload), mode="solo")
    assert qs[0].why == "" and qs[0].from_audio is False


def test_detect_questions_uses_streaming_when_available():
    """P4: se il provider espone chat_json_stream lo usa (il read-timeout si resetta a ogni
    token); fallback a chat_json per i provider che non lo implementano (fake)."""

    class _StreamProv:
        def __init__(self):
            self.stream_calls = 0
            self.json_calls = 0
            self.got_cancel = "missing"

        def chat_json(self, system, user):
            self.json_calls += 1
            return {"questions": []}

        def chat_json_stream(self, system, user, *, json_schema=None, on_delta=None, should_cancel=None):
            self.stream_calls += 1
            self.got_cancel = should_cancel
            return {"questions": [{"id": "q1", "text": "Budget?", "priority": "high"}]}

    p = _StreamProv()
    sentinel = lambda: False  # noqa: E731 — should_cancel passabile e onorato
    qs = IV.detect_questions(_analysis(), "t", provider=p, mode="solo", should_cancel=sentinel)
    assert p.stream_calls == 1 and p.json_calls == 0, "deve usare lo streaming quando disponibile"
    assert p.got_cancel is sentinel, "should_cancel deve arrivare allo streaming"
    assert qs and qs[0].id == "q1"


def test_build_refinement_only_answered_flat_dict():
    qs = [IV.Question(id="q1", text="Budget?"), IV.Question(id="q2", text="Chi legge?")]
    flat = IV.build_refinement(qs, answers={"q1": "  ", "q2": "il team"}, skipped=[])
    assert flat == {"Chi legge?": "il team"}


def test_da_chiarire_markers_from_skipped_and_empty():
    qs = [
        IV.Question(id="q1", text="Budget?"),
        IV.Question(id="q2", text="Chi legge?"),
        IV.Question(id="q3", text="Scadenza?"),
    ]
    markers = IV.da_chiarire_markers(qs, answers={"q2": "il team"}, skipped=["q1"])
    assert markers == [
        "Budget? (domanda saltata in rifinitura)",
        "Scadenza? (domanda saltata in rifinitura)",
    ]
