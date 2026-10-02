"""Dai turni della diarization alle righe della trascrizione.

La diarization produce TURNI `(start, end, speaker)` che non coincidono con i segmenti di
Whisper: qui i due mondi si incontrano. Tutto cio' che sta in questo modulo e' PURO — niente
modelli, niente I/O — perche' e' il punto in cui un errore diventa invisibile: una frase
attribuita alla persona sbagliata sembra corretta e non lo e'.

Regola conservativa: un segmento prende lo speaker del turno che lo copre di PIU'; se non lo
copre nessuno resta **senza** etichetta. Nessuna etichetta e' meglio di un'etichetta falsa.
"""

from typing import NamedTuple

from vokari import i18n


class Turn(NamedTuple):
    start: float
    end: float
    speaker: int


def speaker_label(speaker: int, lang: str = "it") -> str:
    """`0` -> «Interlocutore 1» / «Speaker 1». Si numera da 1: chi legge non conta da zero."""
    return i18n.t("diarize.speaker", lang, n=speaker + 1)


def _overlap(a_lo: float, a_hi: float, b_lo: float, b_hi: float) -> float:
    return max(0.0, min(a_hi, b_hi) - max(a_lo, b_lo))


def assign_speakers(segments: list[dict], turns: list[Turn]) -> list[dict]:
    """Copia dei segmenti con `speaker` valorizzato dove un turno li copre. Non muta l'input."""
    if not turns:
        return segments
    out: list[dict] = []
    for seg in segments:
        lo, hi = float(seg.get("start", 0.0)), float(seg.get("end", 0.0))
        migliore, copertura = None, 0.0
        for t in turns:
            ov = _overlap(lo, hi, t.start, t.end)
            if ov > copertura:
                migliore, copertura = t.speaker, ov
        out.append({**seg, "speaker": migliore})
    return out


def transcript_with_speakers(segments: list[dict], *, lang: str = "it") -> str:
    """Trascrizione come DIALOGO: un turno per persona, frasi consecutive unite.

    E' questo il testo che conviene dare all'LLM di una riunione: «chi dice cosa» cambia il
    senso di una decisione. Senza speaker si comporta come la trascrizione lineare di sempre."""
    righe: list[str] = []
    corrente: int | None = None
    pezzi: list[str] = []
    ha_speaker = False
    for seg in segments:
        testo = " ".join(str(seg.get("text", "")).split())
        if not testo:
            continue
        spk = seg.get("speaker")
        if spk is None:
            spk = corrente  # una frase non attribuita resta col turno in corso
        else:
            ha_speaker = True
        if spk != corrente and pezzi:
            righe.append((f"{speaker_label(corrente, lang)}: " if corrente is not None else "") + " ".join(pezzi))
            pezzi = []
        corrente = spk
        pezzi.append(testo)
    if pezzi:
        righe.append((f"{speaker_label(corrente, lang)}: " if corrente is not None else "") + " ".join(pezzi))
    if not ha_speaker:
        return " ".join(righe)
    return "\n".join(righe)
