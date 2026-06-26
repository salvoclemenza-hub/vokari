"""Modello Session: mirror snake_case dell'interfaccia TS (handoff §7). Bozza per M2."""

import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime


@dataclass
class Session:
    id: str
    title: str = "Sessione senza titolo"
    created_at: str = ""  # ISO 8601 UTC
    mode: str = "solo"  # 'solo' | 'riunione'
    source: str = "mic"  # 'mic' | 'system' | 'both'
    duration_ms: int = 0
    model: str = ""
    language: str = "auto"  # 'auto' | 'it' | 'en'
    status: str = "idle"  # idle|recording|paused|transcribing|analyzing|refining|ready
    audio_path: str = ""  # LOCALE, mai uploadato
    transcript: str | None = None
    markers: list[dict] = field(default_factory=list)  # [{t_ms, label}]
    refinement: dict | None = None  # {answers: {...}, skipped: [...]}
    artifacts: dict | None = None  # {briefing_md, recap_md, obsidian_note}
    word_count: int | None = None
    # L02: l'Analysis JSON (model_dump di vokari.analyze.schema.Analysis) e i marcatori
    # [DA CHIARIRE] persistiti → abilitano il re-export render-only degli artefatti dal
    # risultato LLM salvato, anche dopo che il Job è stato abbandonato/cancellato.
    analysis: dict | None = None
    da_chiarire: list[str] = field(default_factory=list)
    briefing_path: str = ""  # L02: percorso dell'ultimo briefing.md scritto (re-export/generazione)

    @classmethod
    def new(
        cls,
        *,
        title: str = "Sessione senza titolo",
        mode: str = "solo",
        source: str = "mic",
        model: str = "",
        language: str = "auto",
    ) -> "Session":
        return cls(
            id=uuid.uuid4().hex,
            title=title,
            created_at=datetime.now(UTC).isoformat(),
            mode=mode,
            source=source,
            model=model,
            language=language,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def from_transcript_result(
        cls, result: dict, *, mode: str = "solo", title: str = "Sessione senza titolo"
    ) -> "Session":
        text = result.get("text", "")
        s = cls.new(title=title, mode=mode, model=result.get("model", ""), language=result.get("language", "auto"))
        s.audio_path = result.get("source", "")
        s.transcript = text
        s.word_count = len(text.split())
        s.duration_ms = round(result.get("duration_s", 0) * 1000)
        s.status = "transcribed"
        return s
