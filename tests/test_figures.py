"""Il consolidamento (reduce) non deve portare via i NUMERI.

Misurato il 24/09/2026 su una registrazione reale (map qwen2.5:7b + reduce granite4.2:8b):
il briefing passava da 9 a 23 elementi, ma per strada sparivano una data di presentazione e
una forbice min-max. Le cifre sono la parte di un briefing che nessuno puo' ricostruire a
memoria: se erano nell'unione grezza e non sono nel consolidato, tornano indietro.
"""

from vokari.analyze import figures
from vokari.analyze.schema import Analysis, Decision, NextStep


def test_figures_in_finds_plain_numbers_and_percentages():
    assert figures.figures_in("consegna in 15 giorni, scarto al 34%") == {"15", "34"}


def test_figures_in_normalizes_thousands_separator():
    """«1.200 €» e «1200 euro» sono lo stesso numero: non deve sembrare perso."""
    assert figures.figures_in("1.200 €") == figures.figures_in("1200 euro") == {"1200"}


def test_figures_in_keeps_decimals_distinct():
    assert figures.figures_in("1,5 tonnellate") == {"1.5"}


def test_figures_in_ignores_text_without_numbers():
    assert figures.figures_in("nessuna cifra qui") == set()


def _merged() -> Analysis:
    return Analysis(
        key_ideas=["Presentazione il 15/10", "Il mercato tedesco è interessato"],
        decisions=[Decision(title="Prezzo", decision="forbice tra 1,20 e 1,60 al kg")],
        open_questions=["Chi firma?"],
        next_steps=[NextStep(task="Inviare il campione entro il 30/09")],
    )


def test_restores_element_whose_figures_vanished():
    out = Analysis(key_ideas=["Presentazione prevista", "Interesse dall'estero"])
    figures.restore_lost_figures(_merged(), out)
    assert any("15/10" in k for k in out.key_ideas), "la data non può sparire in silenzio"


def test_does_not_duplicate_when_figures_survived_reworded():
    out = Analysis(key_ideas=["La presentazione si terrà il 15/10 a Milano"])
    figures.restore_lost_figures(_merged(), out)
    assert len(out.key_ideas) == 1, "la cifra c'è già: il consolidamento ha fatto il suo lavoro"


def test_does_not_restore_elements_without_figures():
    """Accorpare voci senza numeri è esattamente ciò che il consolidamento deve poter fare."""
    out = Analysis(key_ideas=["Presentazione il 15/10"])
    figures.restore_lost_figures(_merged(), out)
    assert all("mercato tedesco" not in k for k in out.key_ideas)


def test_restores_across_all_structured_lists():
    out = Analysis(
        key_ideas=["Presentazione il 15/10"],
        decisions=[Decision(title="Prezzo", decision="da concordare")],
        next_steps=[NextStep(task="Inviare il campione")],
    )
    figures.restore_lost_figures(_merged(), out)
    assert any("1,20" in d.decision for d in out.decisions)
    assert any("30/09" in n.task for n in out.next_steps)


def test_returns_the_restored_items_for_the_caller():
    out = Analysis(key_ideas=["Presentazione prevista"])
    restored = figures.restore_lost_figures(_merged(), out)
    assert len(restored) == 3  # idea + decisione + next step, tutti con cifre sparite
