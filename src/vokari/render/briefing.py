"""Renderer JSON Analysis -> briefing.md (spec §8.1). Consumatore = LLM (tag XML ok).

`app_lang` (it|en) localizza intestazioni/istruzioni dell'artefatto. È SEPARATO da `language`
(lingua dell'audio, va solo nel frontmatter). Default "it" → output verbatim alle versioni
storiche (anti-regressione)."""

import json

from vokari import i18n
from vokari import markers as markers_mod
from vokari.analyze.schema import Analysis


def _instruction(meta_type: str, app_lang: str) -> str:
    key = "briefing.instr_meeting" if meta_type == "meeting" else "briefing.instr_solo"
    return i18n.t(key, app_lang)


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


def _open_questions_block(a: Analysis, app_lang: str) -> str:
    lines = [f"{i + 1}. {q}" for i, q in enumerate(a.open_questions)] or [i18n.t("briefing.none", app_lang)]
    h = i18n.t("briefing.open_questions_h", app_lang)
    return f"<open_questions>\n## {h}\n" + "\n".join(lines) + "\n</open_questions>"


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
    markers: list[dict] | None = None,
    app_lang: str = "it",
) -> str:
    a = analysis
    na = i18n.t("common.na", app_lang)
    why = i18n.t("common.why_inline", app_lang)
    by = i18n.t("common.by_inline", app_lang)
    out: list[str] = [
        _frontmatter(a, source, transcription_model, llm_model, session_id, language=language, word_count=word_count),
        "",
    ]

    instruction = _instruction(a.meta.type, app_lang)
    out.append(f"<session_instruction>\n{instruction}\n</session_instruction>\n")

    # purpose (comprensione-prima): lo SCOPO in cima, così il consumatore LLM lo vede subito.
    # Omesso se vuoto (analisi pre-purpose) per non mostrare un blocco vuoto.
    if a.purpose:
        out.append(f"<purpose>\n## {i18n.t('briefing.purpose_h', app_lang)}\n{a.purpose}\n</purpose>\n")

    out.append(f"<context>\n## {i18n.t('briefing.context_h', app_lang)}\n" + (a.context or na) + "\n</context>\n")

    dec_lines = [
        ("- **" + d.title + "** — " if d.title else "- ")
        + d.decision
        + (f" _({why}: {d.rationale})_" if d.rationale else "")
        for d in a.decisions
    ] or [i18n.t("briefing.decisions_empty", app_lang)]
    out.append(
        f"<decisions>\n## {i18n.t('briefing.decisions_h', app_lang)}\n" + "\n".join(dec_lines) + "\n</decisions>\n"
    )

    summary = [f"## {i18n.t('briefing.summary_h', app_lang)}"]
    summary += [f"- {i}" for i in a.key_ideas] or [f"- {i18n.t('briefing.no_key_ideas', app_lang)}"]
    if a.entities:
        label = i18n.t("briefing.entities_label", app_lang)
        summary.append(
            f"\n**{label}** " + ", ".join(f"{e.name} ({i18n.entity_type_label(e.type, app_lang)})" for e in a.entities)
        )
    out.append("<session_summary>\n" + "\n".join(summary) + "\n</session_summary>\n")

    out.append(_open_questions_block(a, app_lang) + "\n")

    dc_label = i18n.t("briefing.to_clarify", app_lang)
    for marker in da_chiarire or []:
        out.append(f"> [{dc_label}: {marker}]")
    if da_chiarire:
        out.append("")

    steps = []
    for s in a.next_steps:
        if not s.task.strip():
            continue
        owner = f" — {s.owner}" if s.owner else ""
        deadline = f" ({by} {s.deadline})" if s.deadline else ""
        steps.append(f"- [ ] {s.task}{owner}{deadline}")
    placeholder = f"- [ ] {i18n.t('briefing.no_next_steps', app_lang)}"
    out.append(f"## {i18n.t('briefing.next_steps_h', app_lang)}\n" + ("\n".join(steps) or placeholder) + "\n")

    mk_lines = markers_mod.marker_lines(markers)
    if mk_lines:
        out.append(
            f"<user_markers>\n## {i18n.t('briefing.markers_h', app_lang)}\n"
            + "\n".join(mk_lines)
            + "\n</user_markers>\n"
        )

    out.append(
        f"<raw_transcript>\n## {i18n.t('briefing.transcript_h', app_lang)}\n"
        + (transcript or na)
        + "\n</raw_transcript>"
    )
    return "\n".join(out) + "\n"
