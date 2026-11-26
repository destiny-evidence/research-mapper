"""Evidence map API routes."""

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from research_mapper.api.deps import DbSession, SessionOr404
from research_mapper.engine.models import CurrentArtifact
from research_mapper.models.common import Evidence
from research_mapper.models.mapping import MappingDimensionWithSubTopics
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.enums import SessionReferenceStage
from research_mapper.workflows.evidence_map.hydrate import (
    DESTINY_LOOKUP_CHUNK_SIZE,
    get_evidence,
)
from research_mapper.workflows.evidence_map.models import SessionReference
from research_mapper.workflows.evidence_map.references import (
    VIEWS,
    View,
    ViewName,
    in_cell,
)

router = APIRouter(tags=["evidence map"])


class SessionReferenceOut(BaseModel):
    """One reference and everything the session recorded about it."""

    model_config = ConfigDict(from_attributes=True)

    destiny_id: UUID
    stage: SessionReferenceStage
    provenance: list[dict]
    screening: dict | None
    coordinate: dict | None
    mapping: dict | None
    evidence: Evidence | None = None


class MapCell(BaseModel):
    """How many references share one coordinate."""

    coordinate: dict[str, list[str]]
    count: int


class MapOut(BaseModel):
    """The map's dimensions, and its references counted per coordinate."""

    dimensions: tuple[
        MappingDimensionWithSubTopics,
        MappingDimensionWithSubTopics,
        MappingDimensionWithSubTopics,
    ]
    cells: list[MapCell]
    total: int


def _cells(db: Session, session_id: UUID, dimensions_version: int) -> list[MapCell]:
    """References placed against the dimensions this map is about to render, counted
    per coordinate.

    Both mapping tails stamp the dimensions artifact version they mapped against.
    An older stamp means subtopic names that may no longer exist, which would land
    in no cell while still counting towards the totals printed around the grid.

    However many references there are, there are only so many coordinates: a
    suggested map has at most one per combination of subtopics.
    """
    rows = db.execute(
        select(SessionReference.coordinate, func.count())
        .where(SessionReference.research_session_id == session_id)
        .where(SessionReference.stage == SessionReferenceStage.MAPPED)
        .where(
            SessionReference.mapping["dimensions_version"].astext
            == str(dimensions_version)
        )
        .where(SessionReference.coordinate.is_not(None))
        .group_by(SessionReference.coordinate)
    ).all()
    return [MapCell(coordinate=coordinate, count=count) for coordinate, count in rows]


def _hydrate(destiny_ids: list[UUID]) -> dict[UUID, Evidence]:
    evidence: dict[UUID, Evidence] = {}
    for page in get_evidence(destiny_ids):
        evidence.update(page)
    return evidence


@router.get("/sessions/{session_id}/map/")
def read_map(db: DbSession, research_session: SessionOr404) -> MapOut:
    """Get the evidence map: its dimensions and how many references sit at each
    coordinate. Which references those are is the references endpoint's business,
    a page at a time, so the map costs no DESTINY lookups at all.
    """
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

    cells = _cells(db, research_session.id, artifact.version)
    return MapOut(
        dimensions=(first, second, third),
        cells=cells,
        total=sum(cell.count for cell in cells),
    )


class Bucket(BaseModel):
    """How many of a view's references sit in one of its buckets."""

    bucket: str
    count: int


class Decided(BaseModel):
    """A model that made a view's decisions, and whether it was a dedicated one."""

    model: str
    dedicated: bool | None


class ReferencePage(BaseModel):
    """One page of a view's references, with the counts its table shows."""

    items: list[SessionReferenceOut]
    # The `after` that fetches the next page, or None on the last one.
    next: UUID | None
    total: int
    matched: int
    buckets: list[Bucket]
    decided: list[Decided]


DEFAULT_PAGE = 50
# A page with evidence is one DESTINY lookup; without, it's only rows.
MAX_PAGE_WITH_EVIDENCE = DESTINY_LOOKUP_CHUNK_SIZE
MAX_PAGE = 1000


def _cell_terms(cell: str | None) -> list[tuple[str, str]]:
    if cell is None:
        return []
    try:
        terms = json.loads(cell)
        pairs = [(str(dimension), str(subtopic)) for dimension, subtopic in terms]
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            422, "cell is a JSON list of [dimension, subtopic]"
        ) from exc
    return pairs


@router.get("/sessions/{session_id}/references/")
def list_references(
    db: DbSession,
    research_session: SessionOr404,
    view: ViewName = "all",
    bucket: str | None = None,
    cell: str | None = None,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = DEFAULT_PAGE,
    include_evidence: bool = False,
) -> ReferencePage:
    """A page of the session's references, as one step's table sees them.

    `view` picks the table's subset and buckets; `bucket` and `cell` (a JSON list of
    `[dimension, subtopic]` pairs) narrow it; `after` is the previous page's `next`.
    Only the page's own references are looked up in DESTINY, when asked for.
    """
    if include_evidence and limit > MAX_PAGE_WITH_EVIDENCE:
        msg = f"a page with evidence holds at most {MAX_PAGE_WITH_EVIDENCE}"
        raise HTTPException(422, msg)
    chosen = VIEWS[view]
    in_view = [
        SessionReference.research_session_id == research_session.id,
        *chosen.where,
    ]
    narrowed = [*in_view, *in_cell(_cell_terms(cell))]
    if bucket is not None:
        if chosen.slice is None:
            raise HTTPException(422, f"the {view} view has no buckets")
        narrowed.append(chosen.slice.of == bucket)

    def count(conditions) -> int:
        return db.execute(
            select(func.count()).select_from(SessionReference).where(*conditions)
        ).scalar_one()

    page = select(SessionReference).where(*narrowed)
    if after is not None:
        page = page.where(SessionReference.id > after)
    rows = (
        db.execute(page.order_by(SessionReference.id).limit(limit + 1)).scalars().all()
    )
    more = len(rows) > limit
    rows = rows[:limit]
    items = [SessionReferenceOut.model_validate(row) for row in rows]
    if include_evidence and items:
        evidence = _hydrate([item.destiny_id for item in items])
        for item in items:
            item.evidence = evidence.get(item.destiny_id)

    return ReferencePage(
        items=items,
        next=rows[-1].id if more else None,
        total=count(in_view),
        matched=count(narrowed),
        buckets=_buckets(db, chosen, in_view),
        decided=_decided(db, chosen, in_view),
    )


def _buckets(db: Session, view: View, conditions: list) -> list[Bucket]:
    """The view's buckets in their slice's order, leaving out the empty ones."""
    if view.slice is None:
        return []
    rows = db.execute(
        select(view.slice.of, func.count()).where(*conditions).group_by(view.slice.of)
    ).all()
    counts: dict[str, int] = {name: count for name, count in rows}
    return [
        Bucket(bucket=name, count=counts[name])
        for name in view.slice.order
        if counts.get(name)
    ]


def _decided(db: Session, view: View, conditions: list) -> list[Decided]:
    """Each distinct model that made the view's decisions."""
    if view.decided is None:
        return []
    decision = getattr(SessionReference, view.decided)
    model = decision["model"].astext
    rows = db.execute(
        select(model, decision["dedicated"])
        .where(*conditions, model.is_not(None))
        .distinct()
        .order_by(model)
    ).all()
    return [Decided(model=name, dedicated=dedicated) for name, dedicated in rows]
