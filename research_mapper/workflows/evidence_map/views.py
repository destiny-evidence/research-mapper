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


@dataclass(frozen=True, slots=True)
class CoordinateRow:
    destiny_id: UUID
    coordinate: dict[str, list[str]]
    reasoning: str
    dimensions_version: int
