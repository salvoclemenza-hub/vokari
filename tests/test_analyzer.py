import pytest

from vokari.analyze import analyzer
from vokari.analyze.schema import Analysis
from vokari.llm.base import LLMError


class _FakeProvider:
    def __init__(self):
        self.json_calls = 0
        self.text_calls = 0

    def chat_json(self, system, user, *, json_schema=None):
        self.json_calls += 1
        return {
            "meta": {"type": "solo", "title": "T"},
            "context": "ctx",
            "key_ideas": ["i1"],
            "decisions": [],
            "open_questions": [],
            "next_steps": [],
            "entities": [],
        }

    def chat_text(self, system, user):
        self.text_calls += 1
        return f"riassunto-{self.text_calls}"


def test_analyze_returns_validated_analysis():
    p = _FakeProvider()
    a = analyzer.analyze("trascrizione breve", mode="solo", provider=p)
    assert isinstance(a, Analysis)
    assert a.meta.title == "T" and a.key_ideas == ["i1"]
    assert p.json_calls == 1 and p.text_calls == 0  # niente fallback


def test_analyze_short_text_skips_chunking(monkeypatch):
    p = _FakeProvider()
    analyzer.analyze("una due tre", mode="solo", provider=p)
    assert p.text_calls == 0


def test_analyze_long_text_uses_chunk_summary(monkeypatch):
    monkeypatch.setattr(analyzer, "FALLBACK_WORD_THRESHOLD", 3)
    monkeypatch.setattr(analyzer, "SUMMARY_CHUNK_WORDS", 2)
    p = _FakeProvider()
    analyzer.analyze("una due tre quattro cinque", mode="solo", provider=p)
    assert p.text_calls >= 1  # ha riassunto i chunk
    assert p.json_calls == 1  # poi una sola analisi finale


def test_analyze_summarizes_when_over_provider_budget():
    """Trascrizione oltre il budget di contesto del provider → riassunta PRIMA (no troncamento
    silenzioso), poi una sola analisi finale. È la difesa al limite ctx del modello locale."""

    class _BudgetProvider(_FakeProvider):
        def context_budget_tokens(self):
            return 10  # budget minuscolo → qualsiasi trascrizione lo supera

    p = _BudgetProvider()
    analyzer.analyze("una due tre quattro cinque sei sette otto nove dieci", mode="solo", provider=p)
    assert p.text_calls >= 1, "doveva riassumere a tratti prima dell'analisi"
    assert p.json_calls == 1, "poi una sola analisi finale sul riassunto"


def test_analyze_within_budget_does_not_summarize():
    """Sotto il budget del provider: nessun riassunto, analisi diretta sulla trascrizione intera."""

    class _BudgetProvider(_FakeProvider):
        def context_budget_tokens(self):
            return 30000  # ampio → la trascrizione breve ci sta comodamente

    p = _BudgetProvider()
    analyzer.analyze("trascrizione breve", mode="solo", provider=p)
    assert p.text_calls == 0
    assert p.json_calls == 1


def test_analyze_raises_clear_error_on_non_dict_response():
    """Un LLM locale può restituire una lista invece di un oggetto: deve dare un LLMError
    leggibile (la pipeline lo mappa a status=error), non un crash pydantic criptico."""

    class _NonDict:
        def chat_json(self, system, user, *, json_schema=None):
            return ["non", "un", "dict"]

        def chat_text(self, system, user):
            return ""

    with pytest.raises(LLMError):
        analyzer.analyze("testo qualsiasi", mode="solo", provider=_NonDict())


class _TwoPass:
    """1° passo: purpose=`first`; 2° passo (verifica): purpose=`second`."""

    def __init__(self, first: str, second: str, meta_type: str = "solo"):
        self.first, self.second, self.meta_type = first, second, meta_type
        self.calls = 0

    def chat_json(self, system, user, *, json_schema=None):
        self.calls += 1
        purpose = self.first if self.calls == 1 else self.second
        return {
            "meta": {"type": self.meta_type, "title": "T"},
            "purpose": purpose,
            "context": "ctx",
            "key_ideas": [],
            "decisions": [],
            "open_questions": [],
            "next_steps": [],
            "entities": [],
        }

    def chat_text(self, system, user):
        return ""


def test_coverage_adds_missing_when_main_point_weak():
    """verify=True + purpose vuoto al 1° passo (mode solo) → 2° passo di copertura valorizza purpose."""
    p = _TwoPass(first="", second="Decidere il budget del progetto X")
    a = analyzer.analyze("trascrizione", mode="solo", verify=True, provider=p)
    assert p.calls == 2  # ha eseguito il secondo passo
    assert a.purpose == "Decidere il budget del progetto X"


def test_verify_false_skips_coverage_pass():
    """Senza verify, nessun secondo passo anche se il purpose è vuoto."""
    p = _TwoPass(first="", second="qualcosa")
    analyzer.analyze("t", mode="solo", verify=False, provider=p)
    assert p.calls == 1


def test_verify_skips_second_pass_when_purpose_strong_and_solo():
    """Gate: purpose già valorizzato + mode solo → niente secondo passo (risparmio costo)."""
    p = _TwoPass(first="Scopo chiaro e completo", second="altro")
    a = analyzer.analyze("t", mode="solo", verify=True, provider=p)
    assert p.calls == 1
    assert a.purpose == "Scopo chiaro e completo"


def test_verify_runs_second_pass_for_riunione_even_with_purpose():
    """Gate: riunione → secondo passo anche con purpose valorizzato (le decisioni pesano)."""
    p = _TwoPass(first="bozza", second="scopo raffinato", meta_type="meeting")
    a = analyzer.analyze("t", mode="riunione", verify=True, provider=p)
    assert p.calls == 2
    assert a.purpose == "scopo raffinato"


def test_analyze_passes_markers_to_prompt():
    """analyze inoltra i markers a build_user: il prompt utente li contiene."""
    from vokari.analyze import analyzer as az
    from vokari.analyze.schema import Analysis

    captured = {}

    class FakeProvider:
        def chat_json(self, system, user, *, json_schema):
            captured["user"] = user
            return Analysis(purpose="ok").model_dump()

    az.analyze("testo", mode="solo", provider=FakeProvider(), markers=[{"t_ms": 5_000, "label": "Punto A"}])
    assert "Punto A" in captured["user"]
    assert "00:05" in captured["user"]


def test_analyze_long_text_warns_and_honors_cancel(monkeypatch):
    """Fallback testi enormi: emette un warning informativo e si ferma se should_cancel()."""
    monkeypatch.setattr(analyzer, "FALLBACK_WORD_THRESHOLD", 3)
    monkeypatch.setattr(analyzer, "SUMMARY_CHUNK_WORDS", 2)
    p = _FakeProvider()
    events: list[tuple[str, dict]] = []
    analyzer.analyze(
        "una due tre quattro cinque sei",
        mode="solo",
        provider=p,
        emit=lambda ev, payload: events.append((ev, payload)),
        should_cancel=lambda: True,
    )  # annullato subito → nessun chunk riassunto
    assert any(ev == "warning" for ev, _ in events)
    assert p.text_calls == 0  # should_cancel ferma prima di chiamare l'LLM


def test_is_sparse_true_when_all_lists_empty():
    from vokari.analyze.analyzer import is_sparse_analysis
    from vokari.analyze.schema import Analysis, Meta

    a = Analysis(meta=Meta(type="solo", title="T"))
    a.purpose = "uno scopo pieno"  # stringhe piene...
    a.context = "del contesto"
    # ...ma TUTTE le liste vuote → sparse
    assert is_sparse_analysis(a) is True


def test_is_sparse_false_when_any_list_has_content():
    from vokari.analyze.analyzer import is_sparse_analysis
    from vokari.analyze.schema import Analysis

    assert is_sparse_analysis(Analysis(key_ideas=["un'idea"])) is False
    from vokari.analyze.schema import Decision

    assert is_sparse_analysis(Analysis(decisions=[Decision(decision="fare X")])) is False
    assert is_sparse_analysis(Analysis(open_questions=["e i costi?"])) is False
    from vokari.analyze.schema import NextStep

    assert is_sparse_analysis(Analysis(next_steps=[NextStep(task="chiamare Y")])) is False
    from vokari.analyze.schema import Entity

    assert is_sparse_analysis(Analysis(entities=[Entity(name="VMM")])) is False


def test_is_sparse_true_on_default_analysis():
    from vokari.analyze.analyzer import is_sparse_analysis
    from vokari.analyze.schema import Analysis

    assert is_sparse_analysis(Analysis()) is True
