from typing import Annotated

from pydantic import Field, BaseModel

IRI = Annotated[str, Field(pattern=r"^https?://")]


class Concept(BaseModel):
    """One taxonomy concept."""

    local_ref: str  # the local, simpler ID of the concept for easy LLM citation
    scheme: str
    label: str
    alt_labels: list[str] = []
    detail: str | None = None  # definition or scope_note


class ConceptFilterGroup(BaseModel):
    """One scheme's worth of selected concepts."""

    scheme: str
    concept_local_refs: list[str]
    reason: str
