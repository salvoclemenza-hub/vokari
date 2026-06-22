"""Renderer JSON Analysis -> briefing.md (spec §8.1). Consumatore = LLM (tag XML ok)."""

import json

from vokari.analyze.schema import Analysis

_INSTRUCTIONS: dict[str, str] = {
    "meeting": (
        "Briefing di una riunione aziendale. Parti dalle decisioni prese e dalle open_questions; "
        "usa context e next_steps per coordinare i follow-up. "
        "Dominio: magazzino alimentare B2B (tracciabilità lotti, HACCP, DDT, VMM, lavorazioni MAC)."
    ),
    "solo": (
        "Briefing di un brainstorm individuale. Parti dalle key_ideas e dalle open_questions; "
        "usa next_steps come lista d'azione personale. "
        "Dominio: magazzino alimentare B2B (tracciabilità lotti, HACCP, DDT, VMM, lavorazioni MAC)."
    ),
}


def _yaml_list(items: list[str]) -> str:
    # JSON è YAML valido: quota/escapa ogni stringa (nomi con ':' non rompono il frontmatter).
    return json.dumps(items, ensure_ascii=False)


def _yaml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _frontmatter(
    a: Analysis,
    source: str,
    transcription_model: str,
    llm_model: str,
    session_id: str,
    language: str = "",
    word_count: int = 0,
) -> str:
    m = a.meta
    lines = ["---"]
    if m.date:
        lines.append(f"date: {m.date}")
    if session_id:
        lines.append(f"session_id: {session_id}")
    lines += [
        f"type: {m.type}",
        f"participants: {_yaml_list(m.participants)}",
        f"topic: {_yaml_str(m.title)}",
        f"duration_min: {m.duration_min}",
        f"source: {source}",
        f"transcription_model: {transcription_model}",
        f"llm_model: {llm_model}",
    ]
    if language:
        lines.append(f"language: {language}")
    if word_count:
        lines.append(f"word_count: {word_count}")
    lines.append("---")
    return "\n".join(lines)


def _open_questions_block(a: Analysis) -> str:
    lines = [f"{i + 1}. {q}" for i, q in enumerate(a.open_questions)] or ["(nessuna)"]
    return "<open_questions>\n## Domande aperte\n" + "\n".join(lines) + "\n</open_questions>"


def render_briefing(
    analysis: Analysis,
    *,
    source: str = "",
    transcription_model: str = "",
    llm_model: str = "",
    session_id: str = "",
    transcript: str = "",
    da_chiarire: list[str] | None = None,
    language: str = "",
    word_count: int = 0,
) -> str:
    a = analysis
    out: list[str] = [
        _frontmatter(a, source, transcription_model, llm_model, session_id, language=language, word_count=word_count),
        "",
    ]

    instruction = _INSTRUCTIONS.get(a.meta.type, _INSTRUCTIONS["solo"])
    out.append(f"<session_instruction>\n{instruction}\n</session_instruction>\n")

    # purpose (comprensione-prima): lo SCOPO in cima, così il consumatore LLM lo vede subito.
    # Omesso se vuoto (analisi pre-purpose) per non mostrare un blocco vuoto.
    if a.purpose:
        out.append(f"<purpose>\n## Scopo della sessione\n{a.purpose}\n</purpose>\n")

    out.append("<context>\n## Contesto\n" + (a.context or "(non disponibile)") + "\n</context>\n")

    dec_lines = [
        ("- **" + d.title + "** — " if d.title else "- ")
        + d.decision
        + (f" _(perché: {d.rationale})_" if d.rationale else "")
        for d in a.decisions
    ] or ["(nessuna decisione registrata)"]
    out.append("<decisions>\n## Decisioni prese\n" + "\n".join(dec_lines) + "\n</decisions>\n")

    summary = ["## Sintesi"]
    summary += [f"- {i}" for i in a.key_ideas] or ["- (nessuna idea chiave)"]
    if a.entities:
        summary.append("\n**Entità citate:** " + ", ".join(f"{e.name} ({e.type})" for e in a.entities))
    out.append("<session_summary>\n" + "\n".join(summary) + "\n</session_summary>\n")

    out.append(_open_questions_block(a) + "\n")

    for marker in da_chiarire or []:
        out.append(f"> [DA CHIARIRE: {marker}]")
    if da_chiarire:
        out.append("")

    steps = []
    for s in a.next_steps:
        if not s.task.strip():
            continue
        owner = f" — {s.owner}" if s.owner else ""
        deadline = f" (entro {s.deadline})" if s.deadline else ""
        steps.append(f"- [ ] {s.task}{owner}{deadline}")
    out.append("## Prossimi passi\n" + ("\n".join(steps) or "- [ ] (nessun prossimo passo)") + "\n")

    out.append(
        "<raw_transcript>\n## Trascrizione integrale (ground truth)\n"
        + (transcript or "(non disponibile)")
        + "\n</raw_transcript>"
    )
    return "\n".join(out) + "\n"
