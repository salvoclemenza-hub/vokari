"""Util di dominio per i segnalibri temporali (marker): formattazione condivisa tra i
renderer (`render/*`) e il prompt di analisi (`analyze/prompts.py`). Nessun import di altri
moduli vokari → niente cicli; è la FONTE UNICA del formato `mm:ss`/`h:mm:ss`."""


def fmt_ts(t_ms: int) -> str:
    """`t_ms` → 'mm:ss' (<1h) o 'h:mm:ss' (>=1h). Negativi → '00:00'."""
    s = max(0, int(t_ms)) // 1000
    h, rem = divmod(s, 3600)
    mnt, sec = divmod(rem, 60)
    if h:
        return f"{h}:{mnt:02d}:{sec:02d}"
    return f"{mnt:02d}:{sec:02d}"


def marker_lines(markers: list[dict] | None) -> list[str]:
    """Righe markdown '- mm:ss — label' ordinate per t_ms. Etichetta vuota → solo il tempo.
    Voci non-dict saltate; input falsy → []. Formato comune a tutti gli artefatti (DRY)."""
    valid = [x for x in (markers or []) if isinstance(x, dict)]
    out: list[str] = []
    for mk in sorted(valid, key=lambda x: x.get("t_ms", 0)):
        ts = fmt_ts(mk.get("t_ms", 0))
        label = (mk.get("label") or "").strip()
        out.append(f"- {ts} — {label}" if label else f"- {ts}")
    return out
