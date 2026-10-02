import json

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


def test_thin_analysis_flags_a_shortened_extraction():
    """Il caso reale: un 7B tiene 2 domande su 5 e consegna un briefing che SEMBRA pieno.
    Le liste non sono vuote (is_sparse non scatta), ma per 900 parole di parlato sono poche."""
    from vokari.analyze.analyzer import is_sparse_analysis, is_thin_analysis
    from vokari.analyze.schema import Analysis

    a = Analysis(key_ideas=["un'idea"], open_questions=["e i costi?", "chi firma?"])
    assert is_sparse_analysis(a) is False  # non vuota: l'avviso vecchio non la vedeva
    assert is_thin_analysis(a, 900) is True


def test_thin_analysis_stays_quiet_on_short_recordings():
    """Sotto la soglia di giudizio la varianza è troppo alta: meglio tacere che allarmare."""
    from vokari.analyze.analyzer import is_thin_analysis
    from vokari.analyze.schema import Analysis

    assert is_thin_analysis(Analysis(key_ideas=["una sola idea"]), 120) is False


def test_thin_analysis_never_fires_on_the_repo_gold_files():
    """Guardia anti-falso-allarme: i gold sono il riferimento BUONO. Se la soglia li
    segnalasse, segnalerebbe anche le analisi riuscite e l'avviso diventerebbe rumore."""
    import sys
    from pathlib import Path

    from vokari.analyze.analyzer import is_thin_analysis
    from vokari.analyze.schema import Analysis

    evals = Path(__file__).resolve().parent.parent / "evals"
    if not (evals / "analysis" / "cases.py").exists():
        # `evals/` non viene distribuito (repo pubblico, sdist): senza i gold questa
        # guardia non ha un riferimento da controllare, e saltare e' l'esito onesto.
        pytest.skip("evals/ non presente in questa copia del repo")
    sys.path.insert(0, str(evals))
    from analysis.cases import CASES

    gold_dir = evals / "_shared" / "gold"
    checked = 0
    for case in CASES:
        # i casi nominano il gold con "gold" oppure, quando coincide, col proprio "name"
        gold = case.get("gold") or case.get("name")
        path = gold_dir / f"{gold}.json" if gold else None
        if not path or not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        analysis = Analysis.model_validate(raw.get("analysis", raw))
        words = len(case["transcript"].split())
        assert is_thin_analysis(analysis, words) is False, f"falso allarme sul gold {gold}"
        checked += 1
    assert checked >= 3  # se i gold sparissero, il test non deve passare a vuoto


def test_is_sparse_true_on_default_analysis():
    from vokari.analyze.analyzer import is_sparse_analysis
    from vokari.analyze.schema import Analysis

    assert is_sparse_analysis(Analysis()) is True


# --- Analisi a finestre (map-reduce) -----------------------------------------------------


class _WindowProvider:
    """Restituisce un'idea DIVERSA per ogni chiamata di estrazione, cosi' il test vede se il
    contenuto di tutte le finestre arriva nel risultato. L'ultima chiamata (il consolidamento)
    riceve gli elementi gia' estratti, non la trascrizione: la riconosciamo da li'."""

    def __init__(self):
        self.json_calls = 0
        self.extract_calls = 0
        self.consolidate_calls = 0
        self.consolidated_input = None

    def chat_json(self, system, user, *, json_schema=None):
        self.json_calls += 1
        if "CONSOLIDARE" in user:
            self.consolidate_calls += 1
            self.consolidated_input = user
            return {"meta": {"type": "solo", "title": "consolidata"}, "key_ideas": ["fusa"]}
        self.extract_calls += 1
        return {
            "meta": {"type": "solo", "title": "T"},
            "purpose": f"scopo {self.extract_calls}",
            "key_ideas": [f"idea-finestra-{self.extract_calls}", "idea ripetuta ovunque"],
        }


def _long(words: int) -> str:
    return " ".join(f"parola{i}" for i in range(words))


def test_long_transcript_is_analyzed_in_windows_then_consolidated():
    p = _WindowProvider()
    a = analyzer.analyze(_long(910), mode="solo", provider=p)
    assert p.extract_calls == 3  # 910 parole -> 3 finestre da 350 con overlap 60
    assert p.consolidate_calls == 1
    assert a.key_ideas == ["fusa"]  # vince il consolidamento
    # il consolidamento riceve il contenuto di TUTTE le finestre, non solo dell'ultima
    for i in (1, 2, 3):
        assert f"idea-finestra-{i}" in p.consolidated_input


def test_short_transcript_still_uses_a_single_call():
    """Nessuna regressione sui casi brevi: sotto la soglia il comportamento e' quello storico."""
    p = _WindowProvider()
    analyzer.analyze(_long(120), mode="solo", provider=p)
    assert p.extract_calls == 1 and p.consolidate_calls == 0


def test_windows_survive_a_failing_consolidation():
    """Il consolidamento e' rifinitura: se fallisce si tiene l'unione grezza. Mai perdere
    contenuto gia' estratto per colpa dell'ultimo passo (ADR-041)."""

    class _BrokenConsolidate(_WindowProvider):
        def chat_json(self, system, user, *, json_schema=None):
            if "CONSOLIDARE" in user:
                raise RuntimeError("il modello non risponde")
            return super().chat_json(system, user, json_schema=json_schema)

    a = analyzer.analyze(_long(910), mode="solo", provider=_BrokenConsolidate())
    assert "idea-finestra-1" in a.key_ideas and "idea-finestra-3" in a.key_ideas
    assert a.key_ideas.count("idea ripetuta ovunque") == 1  # dedup deterministico


def test_consolidation_cannot_empty_the_analysis():
    """Un consolidamento che restituisce il vuoto viene scartato: l'unione grezza vince."""

    class _EmptyingConsolidate(_WindowProvider):
        def chat_json(self, system, user, *, json_schema=None):
            if "CONSOLIDARE" in user:
                return {"meta": {"type": "solo", "title": "vuota"}}
            return super().chat_json(system, user, json_schema=json_schema)

    a = analyzer.analyze(_long(910), mode="solo", provider=_EmptyingConsolidate())
    assert a.key_ideas, "l'unione grezza deve sopravvivere a un consolidamento vuoto"


def test_a_failing_window_does_not_lose_the_others():
    class _OneBadWindow(_WindowProvider):
        def chat_json(self, system, user, *, json_schema=None):
            if "parola400" in user and "CONSOLIDARE" not in user:
                raise RuntimeError("finestra persa")
            return super().chat_json(system, user, json_schema=json_schema)

    a = analyzer.analyze(_long(910), mode="solo", provider=_OneBadWindow())
    assert a.key_ideas  # il resto arriva comunque


def test_cancellation_stops_between_windows():
    p = _WindowProvider()
    analyzer.analyze(_long(910), mode="solo", provider=p, should_cancel=lambda: True)
    assert p.extract_calls == 0 and p.consolidate_calls == 0


def test_windowed_false_keeps_the_single_pass():
    p = _WindowProvider()
    analyzer.analyze(_long(910), mode="solo", provider=p, windowed=False)
    assert p.extract_calls == 1 and p.consolidate_calls == 0


def test_split_windows_overlaps_and_covers_everything():
    text = _long(900)
    wins = analyzer.split_windows(text, window=350, overlap=60)
    assert [len(w.split()) for w in wins] == [350, 350, 320]  # passo 290: 0-350, 290-640, 580-900
    # la coda di una finestra ricompare in testa alla successiva (niente frasi tagliate a meta')
    assert wins[0].split()[-60:] == wins[1].split()[:60]
    # ogni parola del testo compare in almeno una finestra
    seen = {w for win in wins for w in win.split()}
    assert seen == set(text.split())


def test_split_windows_clamps_a_too_large_overlap():
    """overlap >= window darebbe passo <= 0: ciclo infinito. Clampato a meta' finestra."""
    wins = analyzer.split_windows(_long(300), window=100, overlap=500)
    assert 1 < len(wins) < 20


def test_merge_analyses_dedups_and_keeps_the_first_purpose():
    from vokari.analyze.schema import Entity, NextStep

    a1 = Analysis(purpose="", key_ideas=["stessa cosa"], next_steps=[NextStep(task="fare X")])
    a2 = Analysis(
        purpose="lo scopo vero",
        key_ideas=["Stessa cosa!", "nuova"],
        entities=[Entity(name="Brio")],
        next_steps=[NextStep(task="fare X")],
    )
    m = analyzer.merge_analyses([a1, a2])
    assert m.key_ideas == ["stessa cosa", "nuova"]  # dedup insensibile a caso/punteggiatura
    assert [s.task for s in m.next_steps] == ["fare X"]
    assert m.purpose == "lo scopo vero"  # primo purpose NON vuoto
    assert [e.name for e in m.entities] == ["Brio"]


def test_clean_entities_drops_pronouns_and_demotes_common_nouns():
    """Visto in produzione nel briefing: "io (persona)", "negozietto (persona)". Ne' qwen ne'
    granite le ripuliscono nel consolidamento — quindi lo facciamo noi, senza LLM."""
    from vokari.analyze.schema import Entity

    a = Analysis(
        entities=[
            Entity(name="io", type="persona"),
            Entity(name="negozietto", type="persona"),
            Entity(name="Marco", type="persona"),
            Entity(name="  ", type="persona"),
            Entity(name="VOKARI", type="progetto"),
        ]
    )
    out = analyzer.clean_entities(a)
    got = [(e.name, e.type) for e in out.entities]
    assert ("io", "persona") not in got and ("  ", "persona") not in got
    assert ("negozietto", "termine") in got  # declassata, non cancellata
    assert ("Marco", "persona") in got and ("VOKARI", "progetto") in got


def test_analyze_cleans_entities_on_the_single_pass_too():
    """Il filtro sta alla fine di analyze(): vale sia a finestre sia a passata singola."""

    class _NoisyEntities:
        def chat_json(self, system, user, *, json_schema=None):
            return {
                "meta": {"type": "solo", "title": "T"},
                "key_ideas": ["i"],
                "entities": [{"name": "io", "type": "persona"}, {"name": "Nancy", "type": "persona"}],
            }

    # la trascrizione nomina Nancy: "io" cade come pronome, Nancy resta perche' e' stata detta
    a = analyzer.analyze("ne parlo con Nancy domani", mode="solo", provider=_NoisyEntities())
    assert [e.name for e in a.entities] == ["Nancy"]


def test_consolidation_can_run_on_a_different_model():
    """ADR-066: il reduce e' UNA chiamata corta per sessione, quindi puo' girare su un modello
    piu' capace senza pesare. Il map resta sul modello veloce."""

    class _Reducer:
        def __init__(self):
            self.calls = 0

        def chat_json(self, system, user, *, json_schema=None):
            self.calls += 1
            return {"meta": {"type": "solo", "title": "dal consolidatore"}, "key_ideas": ["unita"]}

    mapper, reducer = _WindowProvider(), _Reducer()
    a = analyzer.analyze(_long(910), mode="solo", provider=mapper, consolidate_provider=reducer)
    assert mapper.extract_calls == 3 and mapper.consolidate_calls == 0  # il map non consolida
    assert reducer.calls == 1  # una sola chiamata al modello capace
    assert a.key_ideas == ["unita"]


def test_without_a_dedicated_model_the_reduce_stays_on_the_main_one():
    p = _WindowProvider()
    analyzer.analyze(_long(910), mode="solo", provider=p, consolidate_provider=None)
    assert p.consolidate_calls == 1


def test_entities_that_were_never_said_are_dropped():
    """Caso reale (23/09): su una registrazione di 910 parole granite4.2:8b ha prodotto due
    persone — "Sara" e "Luca" — che nella trascrizione non compaiono mai. Un'entita' e' per
    definizione qualcosa che e' stato DETTO."""
    from vokari.analyze.schema import Entity

    transcript = "Marco deve fare un lavoro di pianificazione con Pierpao, poi sentiamo Brio."
    a = Analysis(
        entities=[
            Entity(name="Sara", type="persona"),
            Entity(name="Luca", type="persona"),
            Entity(name="Marco", type="persona"),
            Entity(name="Brio", type="progetto"),
        ]
    )
    got = [e.name for e in analyzer.clean_entities(a, transcript).entities]
    assert got == ["Marco", "Brio"]


def test_grounding_tolerates_the_model_normalising_a_name():
    """Whisper scrive "Pierpao", l'LLM puo' normalizzare in "Pierpaolo": scartarlo sarebbe
    peggio del male che curiamo, quindi il confronto e' sul prefisso."""
    from vokari.analyze.schema import Entity

    a = Analysis(entities=[Entity(name="Pierpaolo", type="persona")])
    assert [e.name for e in analyzer.clean_entities(a, "pianificazione con Pierpao").entities] == ["Pierpaolo"]


def test_without_a_transcript_grounding_is_skipped():
    """Retro-compatibilita': chi chiama senza trascrizione ha il comportamento di prima."""
    from vokari.analyze.schema import Entity

    a = Analysis(entities=[Entity(name="Sconosciuta", type="persona")])
    assert [e.name for e in analyzer.clean_entities(a).entities] == ["Sconosciuta"]


# --- Il passo `verify` non deve mai peggiorare (2026-09-24) -------------------
# Il docstring di `_verify_coverage` prometteva "non peggiora mai", ma: (1) una
# eccezione del provider faceva fallire l'intera analisi, (2) un risultato piu'
# povero sostituiva comunque quello buono (manca la guardia che `_consolidate` ha),
# (3) su testo lungo rispediva TUTTO il testo in una chiamata sola, disfacendo le
# finestre di ADR-064 proprio all'ultimo passo.


class _RichThenPoor:
    """1a chiamata: analisi ricca. 2a (il verify): analisi vuota."""

    def __init__(self, second=None, boom=False):
        self.calls = 0
        self.second = second
        self.boom = boom

    def chat_json(self, system, user, *, json_schema=None):
        self.calls += 1
        if self.calls == 1:
            return {
                "meta": {"type": "meeting", "title": "T"},
                "purpose": "",
                "key_ideas": ["i1", "i2"],
                "decisions": [{"title": "d1", "decision": "fatta"}],
                "open_questions": [],
                "next_steps": [],
                "entities": [],
            }
        if self.boom:
            raise RuntimeError("il modello locale è caduto")
        return self.second

    def chat_text(self, system, user):
        return ""


def test_verify_keeps_first_analysis_when_provider_fails():
    """Il verify è un passo OPZIONALE: se il provider cade, l'analisi già estratta
    non si perde (oggi l'eccezione saliva e il job finiva in error)."""
    p = _RichThenPoor(boom=True)
    a = analyzer.analyze("t", mode="riunione", verify=True, provider=p)
    assert p.calls == 2
    assert a.key_ideas == ["i1", "i2"] and [d.title for d in a.decisions] == ["d1"]


def test_verify_keeps_first_analysis_when_result_is_poorer():
    """Se il verify torna un'analisi vuota, vince quella di prima — stessa guardia
    anti-regressione di `_consolidate`."""
    empty = {
        "meta": {"type": "meeting", "title": "T"},
        "purpose": "scopo",
        "key_ideas": [],
        "decisions": [],
        "open_questions": [],
        "next_steps": [],
        "entities": [],
    }
    p = _RichThenPoor(second=empty)
    a = analyzer.analyze("t", mode="riunione", verify=True, provider=p)
    assert a.key_ideas == ["i1", "i2"] and [d.title for d in a.decisions] == ["d1"]


def test_verify_is_skipped_after_windowed_analysis(monkeypatch):
    """Analisi a finestre = il testo era troppo lungo per una chiamata sola. Il verify
    rimanderebbe TUTTO il testo in un colpo, riaprendo il 'lost in the middle' che le
    finestre hanno chiuso (e costando un'altra passata intera su CPU)."""
    monkeypatch.setattr(analyzer, "ANALYSIS_WINDOW_MIN_WORDS", 3)
    called = {"n": 0}
    monkeypatch.setattr(
        analyzer,
        "_verify_coverage",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or a[1],
    )
    steps: list[str] = []
    analyzer.analyze(
        "una due tre quattro cinque sei",
        mode="riunione",
        verify=True,
        provider=_FakeProvider(),
        on_step=steps.append,
    )
    assert called["n"] == 0
    assert "verify" not in steps


class _MapThenReduce:
    """1a chiamata (la finestra): elementi CON cifre. 2a (il consolidamento): stessi
    elementi riscritti bene ma senza i numeri — il caso misurato il 24/09/2026."""

    def __init__(self):
        self.calls = 0

    def chat_json(self, system, user, *, json_schema=None):
        self.calls += 1
        ideas = ["Presentazione il 15/10 a Milano"] if self.calls == 1 else ["Presentazione a Milano"]
        return {
            "meta": {"type": "solo", "title": "T"},
            "purpose": "scopo",
            "key_ideas": ideas,
            "decisions": [],
            "open_questions": [],
            "next_steps": [],
            "entities": [],
        }

    def chat_text(self, system, user):
        return ""


def test_consolidation_cannot_drop_figures(monkeypatch):
    """Il reduce può riordinare e accorpare, non portarsi via una data."""
    monkeypatch.setattr(analyzer, "ANALYSIS_WINDOW_MIN_WORDS", 3)
    monkeypatch.setattr(analyzer, "ANALYSIS_WINDOW_WORDS", 3)
    monkeypatch.setattr(analyzer, "ANALYSIS_WINDOW_OVERLAP", 1)
    p = _MapThenReduce()
    a = analyzer.analyze("una due tre quattro cinque sei", mode="solo", provider=p)
    assert p.calls >= 2  # è passato dal consolidamento
    assert any("15/10" in k for k in a.key_ideas)


def test_on_stage_exposes_the_raw_merge_and_the_consolidated(monkeypatch):
    """Per misurare il map-reduce serve vedere i DUE risultati: l'unione grezza delle
    finestre e ciò che il consolidamento ne ha fatto. Senza questo gancio un eval dovrebbe
    riscrivere la catena — e misurerebbe una catena diversa da quella che gira davvero."""
    monkeypatch.setattr(analyzer, "ANALYSIS_WINDOW_MIN_WORDS", 3)
    monkeypatch.setattr(analyzer, "ANALYSIS_WINDOW_WORDS", 3)
    monkeypatch.setattr(analyzer, "ANALYSIS_WINDOW_OVERLAP", 1)
    seen: dict = {}
    analyzer.analyze(
        "una due tre quattro cinque sei",
        mode="solo",
        provider=_MapThenReduce(),
        on_stage=lambda stage, a: seen.__setitem__(stage, a),
    )
    assert set(seen) == {"merged", "consolidated"}
    assert any("15/10" in k for k in seen["merged"].key_ideas)
