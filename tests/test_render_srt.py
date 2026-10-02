"""Export SRT: i sottotitoli della registrazione, con i tempi reali dei segmenti.

MacWhisper e gli altri lo danno per scontato; VOKARI aveva i timestamp (li produce
faster-whisper) e li buttava via. Serve per ritrovare un punto nell'audio, per i video,
e per chi deve rileggere una frase sentendola.
"""

from vokari.render.srt import render_srt

SEGMENTI = [
    {"start": 0.0, "end": 2.5, "text": "Buongiorno a tutti."},
    {"start": 2.5, "end": 7.25, "text": "Oggi parliamo della landing page."},
]


def test_renders_index_times_and_text():
    out = render_srt(SEGMENTI)
    assert out.startswith("1\n00:00:00,000 --> 00:00:02,500\nBuongiorno a tutti.\n")
    assert "2\n00:00:02,500 --> 00:00:07,250\nOggi parliamo della landing page." in out


def test_hours_are_not_truncated():
    out = render_srt([{"start": 3661.5, "end": 3663.0, "text": "tardi"}])
    assert "01:01:01,500 --> 01:01:03,000" in out


def test_skips_empty_segments():
    out = render_srt([{"start": 0.0, "end": 1.0, "text": "   "}, *SEGMENTI])
    assert out.startswith("1\n00:00:00,000 --> 00:00:02,500")


def test_collapses_newlines_inside_a_segment():
    """Una riga vuota dentro un blocco spezza il file: i player smettono di leggerlo."""
    out = render_srt([{"start": 0.0, "end": 1.0, "text": "prima\n\nseconda"}])
    assert "prima seconda" in out
    assert "\n\n\n" not in out


def test_empty_input_gives_empty_file():
    assert render_srt([]) == ""


def test_ends_with_a_single_blank_line():
    out = render_srt(SEGMENTI)
    assert out.endswith("\n\n") and not out.endswith("\n\n\n")


def test_prefixes_the_speaker_when_it_is_known():
    out = render_srt(
        [{"start": 0.0, "end": 2.0, "text": "Buongiorno.", "speaker": 0}],
        lang="it",
    )
    assert "Interlocutore 1: Buongiorno." in out


def test_no_prefix_without_a_speaker():
    assert "Interlocutore" not in render_srt(SEGMENTI, lang="it")
