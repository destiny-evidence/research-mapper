"""Evidence map API routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_mapper.api.deps import DbSession, SessionOr404
from research_mapper.engine.models import CurrentArtifact
from research_mapper.models.common import Evidence
from research_mapper.models.mapping import EvidenceMap, MappedEvidence
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.enums import SessionReferenceStage
from research_mapper.workflows.evidence_map.hydrate import get_evidence
from research_mapper.workflows.evidence_map.models import SessionReference

router = APIRouter(tags=["evidence map"])


def _coordinates(db: Session, session_id: UUID) -> dict[UUID, dict[str, list[str]]]:
    rows = db.execute(
        select(SessionReference.destiny_id, SessionReference.coordinate)
        .where(SessionReference.research_session_id == session_id)
        .where(SessionReference.stage == SessionReferenceStage.MAPPED)
        .order_by(SessionReference.id)
    ).all()
    return {row.destiny_id: row.coordinate for row in rows if row.coordinate}


def _hydrate(destiny_ids: list[UUID]) -> dict[UUID, Evidence]:
    evidence: dict[UUID, Evidence] = {}
    for page in get_evidence(destiny_ids):
        evidence.update(page)
    return evidence


@router.get("/sessions/{session_id}/map/")
def read_map(db: DbSession, research_session: SessionOr404) -> EvidenceMap:
    """Get the screened evidence map."""
    artifact = db.execute(
        select(CurrentArtifact)
        .where(CurrentArtifact.research_session_id == research_session.id)
        .where(CurrentArtifact.type == artifacts.DIMENSIONS.name)
    ).scalar_one_or_none()
    if artifact is None:
        raise HTTPException(404, "this session has no map yet")

    dimensions = artifacts.Dimensions.model_validate(artifact.payload).dimensions
    if len(dimensions) != artifacts.DIMENSION_COUNT:
        msg = f"a map needs {artifacts.DIMENSION_COUNT} dimensions, this one has {len(dimensions)}"
        raise HTTPException(500, msg)
    first, second, third = dimensions

    coordinates = _coordinates(db, research_session.id)
    evidence = _hydrate(list(coordinates))
    return EvidenceMap(
        dimensions=(first, second, third),
        mapped_evidence=[
            MappedEvidence(evidence=evidence[destiny_id], coordinate=coordinate)
            for destiny_id, coordinate in coordinates.items()
            if destiny_id in evidence
        ],
    )
