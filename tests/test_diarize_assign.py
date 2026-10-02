"""Attribuzione degli speaker ai segmenti trascritti.

La diarization (sherpa-onnx) produce TURNI `(start, end, speaker)` indipendenti dai segmenti
di Whisper. Il pezzo che conta — e l'unico che può sbagliare in modo silenzioso — è la
proiezione degli uni sugli altri: qui è puro e testato, il resto è I/O.
"""

from vokari.diarize import speakers


def _turno(start, end, spk):
    return speakers.Turn(start=start, end=end, speaker=spk)


SEGMENTI = [
    {"start": 0.0, "end": 3.0, "text": "Buongiorno a tutti."},
    {"start": 3.2, "end": 6.0, "text": "Direi di partire dal magazzino."},
]


def test_assigns_the_speaker_with_the_largest_overlap():
    turni = [_turno(0.0, 3.1, 0), _turno(3.1, 7.0, 1)]
    out = speakers.assign_speakers(SEGMENTI, turni)
    assert [s["speaker"] for s in out] == [0, 1]


def test_a_segment_across_two_turns_goes_to_the_one_that_covers_it_more():
    turni = [_turno(0.0, 1.0, 0), _turno(1.0, 4.0, 1)]
    out = speakers.assign_speakers([{"start": 0.0, "end": 3.0, "text": "x"}], turni)
    assert out[0]["speaker"] == 1


def test_a_segment_outside_every_turn_has_no_speaker():
    """Meglio nessuna etichetta che un'etichetta sbagliata: attribuire una frase alla
    persona sbagliata è il danno peggiore che questa funzione può fare."""
    out = speakers.assign_speakers([{"start": 90.0, "end": 92.0, "text": "x"}], [_turno(0.0, 5.0, 0)])
    assert out[0].get("speaker") is None


def test_does_not_mutate_the_input():
    originali = [dict(s) for s in SEGMENTI]
    speakers.assign_speakers(SEGMENTI, [_turno(0.0, 6.0, 0)])
    assert SEGMENTI == originali


def test_without_turns_the_segments_come_back_untouched():
    assert speakers.assign_speakers(SEGMENTI, []) == SEGMENTI


def test_transcript_groups_consecutive_lines_of_the_same_speaker():
    """All'LLM serve un dialogo leggibile, non una riga per frase: le frasi consecutive
    della stessa persona stanno in un turno solo."""
    segs = [
        {"start": 0.0, "end": 1.0, "text": "Buongiorno.", "speaker": 0},
        {"start": 1.0, "end": 2.0, "text": "Partiamo dal magazzino.", "speaker": 0},
        {"start": 2.0, "end": 3.0, "text": "D'accordo.", "speaker": 1},
    ]
    testo = speakers.transcript_with_speakers(segs, lang="it")
    assert testo == ("Interlocutore 1: Buongiorno. Partiamo dal magazzino.\nInterlocutore 2: D'accordo.")


def test_transcript_falls_back_to_plain_text_without_speakers():
    segs = [{"start": 0.0, "end": 1.0, "text": "Buongiorno."}]
    assert speakers.transcript_with_speakers(segs, lang="it") == "Buongiorno."


def test_speaker_label_is_localised():
    assert speakers.speaker_label(0, "en") == "Speaker 1"
    assert speakers.speaker_label(2, "it") == "Interlocutore 3"
