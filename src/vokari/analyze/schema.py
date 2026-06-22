"""Schema pydantic del JSON di analisi (spec §7). Un'unica analisi -> un Analysis."""

from typing import Literal

from pydantic import BaseModel, Field


class Meta(BaseModel):
    type: Literal["meeting", "solo"] = "solo"
    title: str = ""
    participants: list[str] = Field(default_factory=list)
    duration_min: int = 0
    date: str = ""


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
