"""Fase C i18n (output AI in inglese quando app_language=en).

Il MOTORE deve produrre TUTTO l'output nella lingua dell'app (`app_language`): artefatti
(briefing/recap/obsidian), direttive di lingua nei prompt LLM, messaggi della pipeline.
È SEPARATO da `transcription_language` (lingua dell'audio).

Anti-regressione: il default resta "it" → i renderer/prompt con lingua di default
producono output identico (i test IT esistenti restano verdi). Qui si verifica il ramo EN.
"""

from app import pipeline as P
from app.jobs import Job, JobStore

from vokari import i18n
from vokari.analyze import analyzer as analyzer_mod
from vokari.analyze import fit as fit_mod
from vokari.analyze import interview as IV
from vokari.analyze import prompts
from vokari.analyze.schema import Analysis, Decision, Entity, Meta, NextStep
from vokari.render import briefing as briefing_mod
from vokari.render import obsidian as obs_mod
from vokari.render import recap as recap_mod
from vokari.settings import Settings

# ── Core catalogo i18n ───────────────────────────────────────────────────────


def test_t_returns_italian_by_default():
    assert i18n.t("briefing.open_questions_h") == "Domande aperte"


def test_t_returns_english_when_requested():
    assert i18n.t("briefing.open_questions_h", "en") == "Open questions"


def test_t_falls_back_to_italian_for_unknown_lang():
    assert i18n.t("briefing.open_questions_h", "fr") == "Domande aperte"


def test_t_unknown_key_returns_key():
    assert i18n.t("does.not.exist", "en") == "does.not.exist"


def test_t_supports_format_kwargs():
    # una chiave con placeholder deve interpolare
    msg = i18n.t("pipeline.model_dl_failed", "en", model="large-v3", err="boom")
    assert "large-v3" in msg and "boom" in msg


def test_normalize_lang():
    assert i18n.normalize_lang("EN") == "en"
    assert i18n.normalize_lang("it") == "it"
    assert i18n.normalize_lang("fr") == "it"  # non supportata → default
    assert i18n.normalize_lang("") == "it"
    assert i18n.normalize_lang(None) == "it"


def test_t_format_error_returns_unformatted_template():
    """Placeholder mancante nei kwargs → ritorna il template senza crash (branch except)."""
    # model_dl_failed ha {model} e {err}; passandone solo uno il .format solleva KeyError → template
    out = i18n.t("pipeline.model_dl_failed", "en", err="x")
    assert "{model}" in out


def test_lang_name_known_and_unknown():
    assert i18n.lang_name("en", "it") == "inglese"
    assert i18n.lang_name("en", "en") == "English"
    assert i18n.lang_name("zz", "en") == "zz"  # codice ignoto → grezzo
    assert i18n.lang_name("", "en") == "?"


def test_entity_type_label_fallback():
    assert i18n.entity_type_label("progetto", "en") == "project"
    assert i18n.entity_type_label("sconosciuto", "en") == "sconosciuto"  # fuori-enum → grezzo
    assert i18n.entity_type_label("", "en") == ""


def test_model_desc_and_tags_helpers():
    assert "Best all-rounder" in i18n.model_desc("qwen2.5:7b", "en")
    assert i18n.model_desc("unknown:model", "en") == ""  # fuori-catalogo → ""
    assert i18n.model_tags(["italiano", "json"], "en") == ["Italian", "JSON"]
    assert i18n.model_tags(["weird"], "en") == ["weird"]  # tag senza traduzione → grezzo
    assert i18n.model_tags(None, "en") == []


# ── Renderer in inglese ──────────────────────────────────────────────────────


def _full_analysis() -> Analysis:
    return Analysis(
        meta=Meta(type="meeting", title="Q3 Roadmap", participants=["Ada"], duration_min=30, date="2026-06-25"),
        purpose="Decide the landing page",
        context="Roadmap alignment.",
        key_ideas=["Add a seasonal calendar"],
        decisions=[Decision(title="Beta delay", decision="postponed two weeks", rationale="polish onboarding")],
        open_questions=["Confirm the supplier?"],
        next_steps=[NextStep(task="finalize copy", owner="Ada", deadline="2026-06-30")],
        entities=[Entity(name="Beta", type="progetto", note="private launch")],
    )


def test_render_briefing_english_headers():
    md = briefing_mod.render_briefing(_full_analysis(), transcript="text", app_lang="en")
    assert "## Context" in md
    assert "## Decisions made" in md
    assert "## Open questions" in md
    assert "## Next steps" in md
    assert "## Full transcript" in md
    assert "(project)" in md  # tipo entità tradotto (enum schema resta IT)
    # niente intestazioni italiane residue
    assert "## Contesto" not in md
    assert "## Decisioni prese" not in md
    assert "## Domande aperte" not in md
    assert "(progetto)" not in md


def test_render_briefing_english_da_chiarire_marker():
    md = briefing_mod.render_briefing(
        _full_analysis(), transcript="t", da_chiarire=["Budget 700 or 730?"], app_lang="en"
    )
    assert "[TO CLARIFY: Budget 700 or 730?]" in md
    assert "DA CHIARIRE" not in md


def test_render_briefing_italian_default_unchanged():
    """Default app_lang='it' → output identico a prima (anti-regressione)."""
    md = briefing_mod.render_briefing(_full_analysis(), transcript="t")
    assert "## Contesto" in md
    assert "## Decisioni prese" in md
    assert "## Domande aperte" in md


def test_render_recap_english_headers():
    md = recap_mod.render_recap(_full_analysis(), app_lang="en")
    assert "## In short" in md
    assert "## Decisions" in md
    assert "## Next steps" in md
    assert "## Open questions" in md
    assert "## In breve" not in md
    assert "## Decisioni" not in md


def test_render_recap_english_da_chiarire():
    md = recap_mod.render_recap(_full_analysis(), da_chiarire=["Clarify budget"], app_lang="en")
    assert "## Points to clarify" in md
    assert "Clarify budget" in md
    assert "Punti da chiarire" not in md


def test_render_obsidian_english_headers_and_tags():
    notes = obs_mod.render_obsidian_notes(_full_analysis(), app_lang="en")
    session = notes[0].content
    assert "## Key points" in session
    assert "**Central idea:**" in session
    assert "tags:\n  - session" in session  # tag tradotto
    assert "## Punti chiave" not in session
    decision_note = notes[1].content
    assert "**Decision:**" in decision_note
    assert "**Source:**" in decision_note


def test_render_obsidian_italian_default_tags_unchanged():
    notes = obs_mod.render_obsidian_notes(_full_analysis())
    assert "tags:\n  - sessione" in notes[0].content


# ── Prompt LLM: direttiva di lingua ──────────────────────────────────────────


def test_build_system_english_directive():
    s = prompts.build_system(language="en")
    assert "English" in s


def test_build_system_italian_default():
    s = prompts.build_system()
    assert "italiano" in s.lower()


def test_build_user_english_values_directive():
    u = prompts.build_user("hello", mode="solo", language="en")
    assert "English" in u


def test_interview_build_system_english():
    s = IV.build_system(language="en")
    assert "English" in s


def test_da_chiarire_markers_english():
    qs = [IV.Question(id="q1", text="What is the budget?")]
    markers = IV.da_chiarire_markers(qs, answers={}, skipped=["q1"], language="en")
    assert markers == ["What is the budget? (question skipped during refinement)"]


def test_da_chiarire_markers_italian_default_unchanged():
    qs = [IV.Question(id="q1", text="Budget?")]
    markers = IV.da_chiarire_markers(qs, answers={}, skipped=["q1"])
    assert markers == ["Budget? (domanda saltata in rifinitura)"]


# ── analyzer: la lingua arriva al prompt ─────────────────────────────────────


class _RecProvider:
    """Cattura i system prompt che riceve (per verificare la direttiva di lingua)."""

    def __init__(self):
        self.systems: list[str] = []

    def chat_json(self, system, user, *, json_schema=None):
        self.systems.append(system)
        return {
            "meta": {"type": "solo", "title": "T"},
            "purpose": "uno scopo chiaro",  # purpose pieno → niente secondo passo
            "context": "ctx",
            "key_ideas": ["i1"],
            "decisions": [],
            "open_questions": [],
            "next_steps": [],
            "entities": [],
        }

    def chat_text(self, system, user):
        return ""


def test_analyze_threads_language_to_prompt():
    prov = _RecProvider()
    analyzer_mod.analyze("una trascrizione", mode="solo", provider=prov, language="en")
    assert prov.systems and any("English" in s for s in prov.systems)


def test_analyze_italian_default_no_english_directive():
    prov = _RecProvider()
    analyzer_mod.analyze("una trascrizione", mode="solo", provider=prov)
    assert not any("English" in s for s in prov.systems)


# ── fit: messaggi in inglese ─────────────────────────────────────────────────


class _BudgetProv:
    def context_budget_tokens(self):
        return 2000

    def model_max_ctx(self):
        return 8192


def test_fit_recommendation_english():
    r = fit_mod.assess_fit("x" * 3000, _BudgetProv(), lang="en")
    assert r.level == "summarize"
    assert "English" not in r.recommendation  # sanity: non deve contenere la parola "English" a caso
    # deve essere in inglese (cita Claude, brand invariato) ma senza italiano
    assert "Claude" in r.recommendation
    assert "Per la massima" not in r.reason  # niente italiano


def test_fit_recommendation_italian_default():
    r = fit_mod.assess_fit("x" * 3000, _BudgetProv())
    assert "Claude" in r.recommendation
    assert "fedeltà" in r.recommendation.lower() or "contesto" in r.reason.lower()


# ── pipeline: app_language guida l'intero output (seam reale) ─────────────────


def test_run_processing_english_output_when_app_language_en(tmp_path, monkeypatch):
    """Seam end-to-end: con Settings(app_language='en'), la pipeline produce un briefing in
    inglese E passa al provider la direttiva di lingua inglese. Solo whisper/detect_questions
    finti; analyze+render girano DAVVERO (lezione ADR-010: niente mock dell'intera pipeline)."""
    store = JobStore(jobs_dir=tmp_path / "jobs")
    monkeypatch.setattr(P.models_mod, "is_downloaded", lambda name: True)

    def fake_stream(path, *, model, language, on_segment=None, should_cancel=None):
        if on_segment:
            on_segment(1.0, "spoken text", "spoken text")
        return {"text": "spoken text", "duration_s": 10.0}

    monkeypatch.setattr(P.whisper_mod, "transcribe_stream", fake_stream)
    # 0 domande → genera subito il briefing (render reale). Il fake accetta language (nuovo kwarg).
    monkeypatch.setattr(
        P.interview_mod,
        "detect_questions",
        lambda a, t, *, provider, mode, should_cancel=None, **_kw: [],
    )

    prov = _RecProvider()
    job = store.create(Job.new(str(tmp_path / "a.wav"), model="small", language="it", mode="solo"))
    out = P.run_processing(
        job, store, settings=Settings(briefing_dir=str(tmp_path / "out"), app_language="en"), provider=prov, emit=None
    )

    assert out.status == "ready"
    # il provider ha ricevuto la direttiva inglese (l'analisi è in inglese)
    assert any("English" in s for s in prov.systems), "il prompt di analisi deve chiedere output in inglese"
    # gli artefatti renderizzati sono in inglese
    assert "## Context" in out.briefing_md
    assert "## Next steps" in out.briefing_md
    assert "## Contesto" not in out.briefing_md
