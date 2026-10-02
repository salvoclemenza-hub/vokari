"""Misura DETERMINISTICA di quanto un'analisi è ancorata alla registrazione.

Nasce dalla misura di ADR-066: il consolidamento ha prodotto due persone («Sara», «Luca»)
che nessuno aveva mai nominato. `clean_entities` copre le entità; tutto il resto — idee,
decisioni, prossimi passi — non era controllato da niente. Qui non si cancella: si CONTA,
così gli eval possono dire se una modifica migliora o peggiora, e l'utente riceve un avviso
invece di un briefing con dentro un nome inventato.
"""

from vokari.analyze import fidelity
from vokari.analyze.schema import Analysis, Decision, Meta, NextStep

TRANSCRIPT = (
    "Allora, con Kamil abbiamo visto la landing page. Il budget è di 1.200 euro e la "
    "presentazione è fissata per il 15/10. Marco segue la parte HACCP."
)


def test_flags_a_number_that_was_never_said():
    a = Analysis(key_ideas=["Il budget è di 3.500 euro"])
    found = fidelity.unsupported_items(a, TRANSCRIPT)
    assert len(found) == 1 and "3500" in found[0].missing


def test_accepts_a_number_that_was_said():
    a = Analysis(key_ideas=["Budget 1.200 euro, presentazione il 15/10"])
    assert fidelity.unsupported_items(a, TRANSCRIPT) == []


def test_flags_a_person_who_was_never_named():
    a = Analysis(decisions=[Decision(title="Consegna", decision="La cura Sara con Kamil")])
    found = fidelity.unsupported_items(a, TRANSCRIPT)
    assert len(found) == 1 and "Sara" in found[0].missing


def test_does_not_flag_the_first_word_of_an_item():
    """«Inviare il campione» comincia per maiuscola ma non è un nome proprio: se la si
    segnalasse, ogni elemento del briefing risulterebbe inventato. È il limite accettato
    in cambio della misura: un nome inventato in PRIMA posizione sfugge qui — lo prende
    `clean_entities`, che sulle entità fa il grounding completo."""
    a = Analysis(next_steps=[NextStep(task="Inviare il campione a Kamil")])
    assert fidelity.unsupported_items(a, TRANSCRIPT) == []


def test_a_name_in_first_position_is_a_known_blind_spot():
    a = Analysis(key_ideas=["Sara segue il progetto"])
    assert fidelity.unsupported_items(a, TRANSCRIPT) == []


def test_flags_an_acronym_that_is_not_in_the_recording():
    a = Analysis(open_questions=["Chi aggiorna il DDT?"])
    found = fidelity.unsupported_items(a, TRANSCRIPT)
    assert len(found) == 1 and "DDT" in found[0].missing


def test_accepts_an_acronym_that_is_in_the_recording():
    a = Analysis(open_questions=["Chi aggiorna il manuale HACCP?"])
    assert fidelity.unsupported_items(a, TRANSCRIPT) == []


def test_clean_analysis_has_nothing_to_report():
    a = Analysis(
        meta=Meta(title="Landing page"),
        purpose="Decidere la landing page con Kamil",
        key_ideas=["Budget 1.200 euro"],
    )
    assert fidelity.unsupported_items(a, TRANSCRIPT) == []


def test_report_counts_items_and_losses():
    merged = Analysis(key_ideas=["Budget 1.200 euro", "Presentazione il 15/10"])
    final = Analysis(key_ideas=["Budget 1.200 euro", "Il progetto lo segue Sara"])
    r = fidelity.report(TRANSCRIPT, merged=merged, final=final)
    assert r.n_final == 2 and r.n_merged == 2
    assert r.n_unsupported == 1  # «Sara» non è mai stata nominata
    assert r.n_dropped == 1  # la data del 15/10 non è arrivata in fondo
    assert 0.0 <= r.grounding <= 1.0


# --- Falsi allarmi visti nella prima corsa vera dell'eval (25/09) -------------
# Un elemento strutturato (Decision, NextStep) viene appiattito concatenando i campi:
# «Formato calendario raccolta» + «Adottare un file Excel» ⇒ «Adottare» finisce a meta'
# frase e sembra un nome proprio. Nell'eval erano 5 avvisi su 5 (Adottare, Fornire,
# Comunicare, Mostrare, Fornisce) e in produzione sarebbero arrivati all'utente.


def test_verb_starting_a_second_field_is_not_a_proper_name():
    a = Analysis(
        decisions=[
            Decision(
                title="Formato del calendario di raccolta",
                decision="Adottare un foglio scaricabile",
                rationale="Comunicare la scelta ai rivenditori",
            )
        ]
    )
    assert fidelity.unsupported_items(a, TRANSCRIPT) == []


def test_a_real_product_name_never_said_is_still_flagged():
    """Il perdono vale per la maiuscola di convenzione, non per un nome vero mai pronunciato."""
    a = Analysis(decisions=[Decision(title="Formato del calendario", decision="Adottare un file Excel scaricabile")])
    found = fidelity.unsupported_items(a, TRANSCRIPT)
    assert len(found) == 1 and found[0].missing == ["Excel"]


def test_owner_is_checked_even_if_it_is_the_first_word_of_its_field():
    """Su `owner` la prima parola E' il dato: perdonarla lascerebbe passare una persona inventata."""
    a = Analysis(next_steps=[NextStep(task="Preparare il campione", owner="Genoveffa")])
    found = fidelity.unsupported_items(a, TRANSCRIPT)
    assert len(found) == 1 and found[0].missing == ["Genoveffa"]


def test_owner_that_was_named_is_not_flagged():
    a = Analysis(next_steps=[NextStep(task="Preparare il campione", owner="Marco")])
    assert fidelity.unsupported_items(a, TRANSCRIPT) == []


def test_invented_name_mid_sentence_is_still_flagged():
    a = Analysis(decisions=[Decision(title="Landing page", decision="La scrive Genoveffa entro venerdì")])
    found = fidelity.unsupported_items(a, TRANSCRIPT)
    assert len(found) == 1 and "Genoveffa" in found[0].missing
