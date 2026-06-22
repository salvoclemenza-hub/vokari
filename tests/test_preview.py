"""Test del parser di preview (src/vokari/analyze/preview.py).

`preview_from_partial_json` rende leggibile il JSON PARZIALE che arriva in streaming
durante l'analisi: estrae i VALORI stringa (saltando le chiavi e il blocco meta),
inclusa l'ultima stringa anche se non ancora chiusa (effetto "sta scrivendo").
È un parser tollerante: NON deve mai sollevare su input troncato/non-JSON.
"""

from vokari.analyze.preview import preview_from_partial_json


def test_empty_and_garbage_never_raise():
    assert preview_from_partial_json("") == ""
    assert preview_from_partial_json("   ") == ""
    assert preview_from_partial_json("non un json") == ""
    assert preview_from_partial_json("{") == ""


def test_skips_keys_keeps_values():
    raw = '{"purpose":"Decidere se fare la landing page"}'
    assert preview_from_partial_json(raw) == "Decidere se fare la landing page"


def test_includes_unclosed_trailing_value():
    # valore in corso di scrittura (stringa non chiusa) → mostrato comunque
    raw = '{"purpose":"Decidere se fa'
    assert preview_from_partial_json(raw) == "Decidere se fa"


def test_unclosed_trailing_key_not_shown():
    # una CHIAVE in corso di scrittura non deve comparire (niente nomi di campo)
    raw = '{"purpose":"fatto","key_id'
    assert preview_from_partial_json(raw) == "fatto"


def test_meta_block_is_skipped():
    raw = '{"meta":{"type":"solo","title":"Riunione X"},"purpose":"Lo scopo"}'
    # type/title sono dentro meta → saltati; resta solo lo scopo
    assert preview_from_partial_json(raw) == "Lo scopo"


def test_list_values_each_on_a_line():
    raw = '{"key_ideas":["idea uno","idea due"]}'
    assert preview_from_partial_json(raw) == "idea uno\nidea due"


def test_unclosed_list_value_included():
    raw = '{"key_ideas":["idea uno","idea d'
    assert preview_from_partial_json(raw) == "idea uno\nidea d"


def test_nested_objects_in_array_keep_inner_values():
    raw = '{"decisions":[{"title":"Lancio","decision":"Marzo","rationale":"prima del competitor"}]}'
    assert preview_from_partial_json(raw) == "Lancio\nMarzo\nprima del competitor"


def test_null_values_skipped_naturally():
    raw = '{"next_steps":[{"task":"Scrivere copy","owner":null,"deadline":null}]}'
    assert preview_from_partial_json(raw) == "Scrivere copy"


def test_escaped_quote_inside_value():
    raw = '{"purpose":"Lui ha detto \\"si\\" subito"}'
    assert preview_from_partial_json(raw) == 'Lui ha detto "si" subito'


def test_tolerates_leading_code_fence():
    # alcuni LLM aprono con ```json prima dell'oggetto: lo stream parziale può contenerlo
    raw = '```json\n{"purpose":"Scopo chiaro"'
    assert preview_from_partial_json(raw) == "Scopo chiaro"


def test_full_analysis_shape_ordered():
    raw = (
        '{"meta":{"type":"meeting","title":"T"},'
        '"purpose":"Decidere la data",'
        '"context":"",'
        '"key_ideas":["ridurre i costi"],'
        '"decisions":[{"title":"Data","decision":"Marzo","rationale":""}]}'
    )
    out = preview_from_partial_json(raw)
    # ordine preservato, meta saltato, stringhe vuote ignorate
    assert out == "Decidere la data\nridurre i costi\nData\nMarzo"


def test_whitespace_between_tokens():
    raw = '{ "purpose" : "Con spazi" , "context" : "anche qui" }'
    assert preview_from_partial_json(raw) == "Con spazi\nanche qui"
