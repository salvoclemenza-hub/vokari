"""Segmenti trascritti -> file SRT (sottotitoli).

I tempi li produce gia' faster-whisper: qui si limitano a diventare un formato che il resto
del mondo sa leggere (player, editor video, Premiere/Resolve, YouTube). Puro, nessun LLM.
"""

from vokari.diarize import speakers


def _timestamp(seconds: float) -> str:
    """`3661.5` -> `01:01:01,500`. Le ore NON si troncano: un file lungo resta valido."""
    if seconds < 0:
        seconds = 0.0
    ms_totali = round(seconds * 1000)
    ms = ms_totali % 1000
    tot = ms_totali // 1000
    return f"{tot // 3600:02d}:{tot % 3600 // 60:02d}:{tot % 60:02d},{ms:03d}"


def render_srt(segments: list[dict], *, lang: str = "it") -> str:
    """File SRT dai segmenti `{start, end, text}`. I segmenti vuoti si saltano.

    Se un segmento porta uno `speaker` (attribuzione attiva), il sottotitolo lo dice: e'
    l'informazione che un sottotitolo di riunione deve avere per prima.

    Dentro un blocco non puo' esserci una riga vuota: separa i blocchi, e un player che la
    incontra smette di leggere il resto del file."""
    blocchi: list[str] = []
    for seg in segments:
        testo = " ".join(str(seg.get("text", "")).split())
        if not testo:
            continue
        if seg.get("speaker") is not None:
            testo = f"{speakers.speaker_label(int(seg['speaker']), lang)}: {testo}"
        inizio = _timestamp(float(seg.get("start", 0.0)))
        fine = _timestamp(float(seg.get("end", 0.0)))
        blocchi.append(f"{len(blocchi) + 1}\n{inizio} --> {fine}\n{testo}\n")
    return "\n".join(blocchi) + "\n" if blocchi else ""
