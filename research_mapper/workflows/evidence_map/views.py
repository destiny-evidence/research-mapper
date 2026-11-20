"""Evidence map view models."""

from dataclasses import dataclass
from uuid import UUID

from research_mapper.workflows.evidence_map.enums import SessionReferenceStage


@dataclass(frozen=True, slots=True)
class RefRow:
    destiny_id: UUID
    provenance: dict


@dataclass(frozen=True, slots=True)
class ReferenceView:
    destiny_id: UUID
    stage: SessionReferenceStage
    screening: dict | None
    coordinate: dict | None


@dataclass(frozen=True, slots=True)
class ScreeningRow:
    destiny_id: UUID
    include: bool
    reasoning: str
    criteria_version: int
    # What the verdict was read from, kept so it can be re-thresholded later.
    # The model tells a decision model's probability from a chat model's own.
    probability: float | None = None
    threshold: float | None = None
    model: str | None = None


@dataclass(frozen=True, slots=True)
class CoordinateRow:
    destiny_id: UUID
    coordinate: dict[str, list[str]]
    reasoning: str
    dimensions_version: int
    # What each dimension's subtopic was chosen from: dimension name to its subtopics'
    # probabilities, and the model that gave them. Kept apart from the coordinate,
    # whose shape the API, UI and export rely on.
    probabilities: dict[str, dict[str, float]] | None = None
    model: str | None = None
