"""Renderer JSON Analysis -> recap.md (spec §8.2).

Consumatore = UMANO: prosa pulita, niente tag XML, niente trascrizione integrale.
Stesso `Analysis` del briefing; template diverso (leggibile in trenta secondi).
"""

from vokari.analyze.schema import Analysis


def render_recap(analysis: Analysis, *, title: str = "", da_chiarire: list[str] | None = None) -> str:
    a = analysis
    head = title or a.meta.title or "Sessione"
    out: list[str] = [f"# Recap — {head}"]

    meta_bits: list[str] = []
    if a.meta.date:
        meta_bits.append(a.meta.date)
    if a.meta.duration_min:
        meta_bits.append(f"{a.meta.duration_min} min")
    if a.meta.participants:
        meta_bits.append(", ".join(a.meta.participants))
    if meta_bits:
        out += ["", "_" + " · ".join(meta_bits) + "_"]

    # "In breve" guida con lo SCOPO (purpose, comprensione-prima): è il punto della sessione.
    # Fallback a context/prima idea per analisi pre-purpose. Il contesto, se aggiunge info,
    # segue come paragrafo di supporto.
    in_breve = a.purpose or a.context or (a.key_ideas[0] if a.key_ideas else "_(nessun riassunto)_")
    out += ["", "## In breve", in_breve]
    if a.purpose and a.context and a.context.strip() != a.purpose.strip():
        out += ["", a.context]

    if a.decisions:
        out += ["", "## Decisioni"]
        for d in a.decisions:
            line = f"- **{d.title}** — {d.decision}" if d.title else f"- {d.decision}"
            if d.rationale:
                line += f" (perché: {d.rationale})"
            out.append(line)

    if a.next_steps:
        out += ["", "## Prossimi passi"]
        for s in a.next_steps:
            owner = f" — {s.owner}" if s.owner else ""
            deadline = f" (entro {s.deadline})" if s.deadline else ""
            out.append(f"- {s.task}{owner}{deadline}")

    if a.key_ideas:
        out += ["", "## Discussione chiave"]
        out += [f"- {idea}" for idea in a.key_ideas]

    if a.open_questions:
        out += ["", "## Domande aperte"]
        out += [f"- {q}" for q in a.open_questions]

    if da_chiarire:
        out += ["", "## Punti da chiarire"]
        out += [f"- ⚠ {punto}" for punto in da_chiarire]

    return "\n".join(out).rstrip() + "\n"
