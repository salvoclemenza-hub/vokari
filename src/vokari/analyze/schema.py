"""Schema pydantic del JSON di analisi (spec §7). Un'unica analisi -> un Analysis."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _coerce_enum(value: object, synonyms: dict[str, str], fallback: str) -> str:
    """Normalizza un valore di enum prodotto dall'LLM al set canonico.

    Gli LLM (specie i piccoli Ollama, o quando l'output è in lingua diversa) inventano
    valori fuori dall'enum dichiarato: 'evento'/'luogo'/'organizzazione' per il tipo
    entità, 'riunione'/'person' per i campi tradotti. Un singolo valore fuori-lista NON
    deve far fallire l'INTERA Analysis e perdere il briefing (ADR-038/041). Mappiamo i
    sinonimi noti e bucketizziamo tutto il resto sul fallback. Resta canonico (IT) così
    i renderer / i18n.entity_type_label continuano a mappare la label corretta.
    """
    if isinstance(value, str):
        s = value.strip().lower()
        if s in synonyms:
            return synonyms[s]
    return fallback


# Sinonimi → canonico. Tutto ciò che non è qui (es. 'evento', 'luogo', 'data') → fallback.
_META_TYPE_SYN = {"meeting": "meeting", "riunione": "meeting", "solo": "solo", "individual": "solo"}
_ENTITY_TYPE_SYN = {
    "persona": "persona",
    "person": "persona",
    "people": "persona",
    "persone": "persona",
    "progetto": "progetto",
    "project": "progetto",
    "progetti": "progetto",
    "termine": "termine",
    "term": "termine",
    "termini": "termine",
}


class Meta(BaseModel):
    type: Literal["meeting", "solo"] = "solo"
    title: str = ""
    participants: list[str] = Field(default_factory=list)
    duration_min: int = 0
    date: str = ""

    @field_validator("type", mode="before")
    @classmethod
    def _norm_type(cls, v: object) -> str:
        return _coerce_enum(v, _META_TYPE_SYN, "solo")


class Decision(BaseModel):
    title: str = ""
    decision: str = ""
    rationale: str = ""


class NextStep(BaseModel):
    task: str = ""
    owner: str | None = None
    deadline: str | None = None  # ISO date o null


class Entity(BaseModel):
    name: str = ""
    type: Literal["persona", "progetto", "termine"] = "termine"
    note: str = ""

    @field_validator("type", mode="before")
    @classmethod
    def _norm_type(cls, v: object) -> str:
        return _coerce_enum(v, _ENTITY_TYPE_SYN, "termine")


class Analysis(BaseModel):
    # default_factory: `Analysis()` senza argomenti è valido (meta vuoto) — usato nei
    # rami fallback (es. export_obsidian senza analysis). Un Meta defaultato serializza
    # identico a uno costruito esplicitamente → nessun impatto sul contratto JS.
    meta: Meta = Field(default_factory=Meta)
    # purpose: lo SCOPO/decisione principale della sessione in 1-2 frasi (comprensione-prima).
    # Default "" per retro-compatibilità: gli artefatti/gold pre-esistenti restano validi.
    purpose: str = ""
    context: str = ""
    key_ideas: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    next_steps: list[NextStep] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
