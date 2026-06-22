"""Test del check di idoneità trascrizione↔modello (fit.py, modulo puro, niente I/O).

Il timeout reale del 2026-06-17 (ECO 5.0, qwen2.5:7b, 2h11m) è il sintomo di "trascrizione
troppo grande per il contesto del modello". fit.py rende questo VISIBILE e DECIDIBILE prima
di spendere ore: classifica in ideal / summarize / over_even_summarized.
"""

from vokari.analyze import fit


class _Prov:
    """Provider finto con budget/max contesto noti (come Ollama/Claude reali)."""

    def __init__(self, budget, max_ctx=None, fallback=False):
        self._budget = budget
        self._max = max_ctx if max_ctx is not None else budget + 2048
        self._ctx_is_fallback = fallback

    def context_budget_tokens(self):
        return self._budget

    def model_max_ctx(self):
        return self._max


def test_assess_fit_ideal_for_short_transcript_within_budget():
    r = fit.assess_fit("una breve trascrizione di prova", _Prov(budget=30000, max_ctx=32768))
    assert r.level == "ideal"
    assert r.n_chunks == 0
    assert r.recommendation == ""
    assert r.budget == 30000 and r.ctx_max == 32768
    assert r.tokens_est == len("una breve trascrizione di prova") // fit.CHARS_PER_TOKEN + fit.PROMPT_OVERHEAD_TOKENS


def test_assess_fit_summarize_when_over_budget_but_summary_fits():
    # ~500 "parole" → 1 chunk; tokens_est > budget ma il riassunto (1*400+overhead) ci sta
    r = fit.assess_fit("x" * 3000, _Prov(budget=2000, max_ctx=8192))
    assert r.level == "summarize"
    assert r.n_chunks == 1
    assert "Claude" in r.recommendation


def test_assess_fit_over_even_summarized_for_huge_transcript():
    big = " ".join(["parola"] * 5000)  # 5000 parole → 3 chunk; anche il riassunto sfora il budget piccolo
    r = fit.assess_fit(big, _Prov(budget=2000, max_ctx=8192))
    assert r.level == "over_even_summarized"
    assert r.n_chunks >= 2
    assert r.recommendation


def test_assess_fit_no_budget_methods_is_ideal():
    """Provider senza budget noto (es. fake nei test) → mai riassunto, come il vecchio _needs_summary."""

    class _Bare:
        pass

    r = fit.assess_fit("x" * 100000, _Bare())
    assert r.level == "ideal"
    assert r.n_chunks == 0


def test_assess_fit_propagates_ctx_is_fallback():
    r = fit.assess_fit("x" * 1000, _Prov(budget=100, max_ctx=8192, fallback=True))
    assert r.ctx_is_fallback is True


def test_estimate_from_duration_long_meeting_needs_summary():
    """Preflight: una riunione di ~2h con un modello locale (qwen 32k) NON è ideale → avvisa
    PRIMA di trascrivere (il caso ECO 5.0: 2h11m trascritte per poi riassumere)."""
    prov = _Prov(budget=32768 - 2048, max_ctx=32768)
    r = fit.estimate_from_duration(7840, prov)  # ~2h11m
    assert r.level != "ideal"
    assert r.n_chunks >= 1
    assert "Claude" in r.recommendation


def test_estimate_from_duration_short_is_ideal():
    r = fit.estimate_from_duration(300, _Prov(budget=30000, max_ctx=32768))  # 5 min
    assert r.level == "ideal"
    assert r.n_chunks == 0


def test_estimate_from_duration_scales_with_words_per_min():
    """Più parole/min → più token stimati (la stima è proporzionale alla durata)."""
    slow = fit.estimate_from_duration(3600, _Prov(budget=10_000_000), words_per_min=90)
    fast = fit.estimate_from_duration(3600, _Prov(budget=10_000_000), words_per_min=180)
    assert fast.tokens_est > slow.tokens_est
