"""Renderer JSON Analysis -> recap.md (spec §8.2).

Consumatore = UMANO: prosa pulita, niente tag XML, niente trascrizione integrale.
Stesso `Analysis` del briefing; template diverso (leggibile in trenta secondi).
"""

from vokari import i18n
from vokari import markers as markers_mod
from vokari.analyze.schema import Analysis


def render_recap(
    analysis: Analysis,
    *,
    title: str = "",
    da_chiarire: list[str] | None = None,
    markers: list[dict] | None = None,
    app_lang: str = "it",
) -> str:
    a = analysis
    head = title or a.meta.title or i18n.t("common.session_fallback", app_lang)
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
    in_breve = a.purpose or a.context or (a.key_ideas[0] if a.key_ideas else i18n.t("recap.no_summary", app_lang))
    out += ["", f"## {i18n.t('recap.in_short_h', app_lang)}", in_breve]
    if a.purpose and a.context and a.context.strip() != a.purpose.strip():
        out += ["", a.context]

    why = i18n.t("common.why_inline", app_lang)
    by = i18n.t("common.by_inline", app_lang)

    if a.decisions:
        out += ["", f"## {i18n.t('recap.decisions_h', app_lang)}"]
        for d in a.decisions:
            line = f"- **{d.title}** — {d.decision}" if d.title else f"- {d.decision}"
            if d.rationale:
                line += f" ({why}: {d.rationale})"
            out.append(line)

    if a.next_steps:
        out += ["", f"## {i18n.t('recap.next_steps_h', app_lang)}"]
        for s in a.next_steps:
            owner = f" — {s.owner}" if s.owner else ""
            deadline = f" ({by} {s.deadline})" if s.deadline else ""
            out.append(f"- {s.task}{owner}{deadline}")

    if a.key_ideas:
        out += ["", f"## {i18n.t('recap.key_discussion_h', app_lang)}"]
        out += [f"- {idea}" for idea in a.key_ideas]

    if a.open_questions:
        out += ["", f"## {i18n.t('recap.open_questions_h', app_lang)}"]
        out += [f"- {q}" for q in a.open_questions]

    if da_chiarire:
        out += ["", f"## {i18n.t('common.to_clarify_h', app_lang)}"]
        out += [f"- ⚠ {punto}" for punto in da_chiarire]

    mk_lines = markers_mod.marker_lines(markers)
    if mk_lines:
        out += ["", f"## {i18n.t('common.bookmarks_h', app_lang)}", *mk_lines]

    return "\n".join(out).rstrip() + "\n"
