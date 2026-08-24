from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from research_mapper import workflows
from research_mapper.api.deps import CurrentUser, DbSession, Factory, SessionOr404
from research_mapper.api.schemas import (
    ArtifactOut,
    CreateOperation,
    CreateSession,
    DecisionOut,
    SessionDetail,
    SessionSummary,
)
from research_mapper.engine import runner
from research_mapper.engine.models import (
    CurrentArtifact,
    Decision,
    Operation,
    ResearchSession,
)

router = APIRouter(tags=["sessions"])


@router.post("/sessions/", status_code=status.HTTP_201_CREATED)
def create_session(
    body: CreateSession, db: DbSession, user: CurrentUser
) -> SessionSummary:
    """Start a research session."""
    if body.workflow not in workflows.names():
        raise HTTPException(400, f"unknown workflow: {body.workflow}")
    research_session = ResearchSession(
        user_id=user.id,
        workflow=body.workflow,
        question=body.question,
        community=body.community,
        params=body.params,
    )
    db.add(research_session)
    db.commit()
    return SessionSummary.model_validate(research_session)


@router.get("/sessions/")
def list_sessions(db: DbSession) -> list[SessionSummary]:
    """List sessions, newest first."""
    rows = db.execute(
        select(ResearchSession).order_by(ResearchSession.id.desc())
    ).scalars()
    return [SessionSummary.model_validate(row) for row in rows]


@router.get("/sessions/{session_id}/")
def read_session(db: DbSession, research_session: SessionOr404) -> SessionDetail:
    """A session with the current version of each artifact it holds."""
    artifacts = db.execute(
        select(CurrentArtifact.type, CurrentArtifact.version).where(
            CurrentArtifact.research_session_id == research_session.id
        )
    ).all()
    return SessionDetail(
        **SessionSummary.model_validate(research_session).model_dump(),
        params=research_session.params,
        artifacts={row[0]: row[1] for row in artifacts},
    )


@router.post("/sessions/{session_id}/operations/", status_code=status.HTTP_202_ACCEPTED)
def start_operation(
    body: CreateOperation,
    user: CurrentUser,
    research_session: SessionOr404,
    session_factory: Factory,
) -> dict[str, UUID]:
    """Queue an operation against a session."""
    try:
        operation_id = runner.create_operation(
            research_session.id, user.id, body.type, body.params, session_factory
        )
    except LookupError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"id": operation_id}


@router.get("/sessions/{session_id}/decisions/")
def list_decisions(
    db: DbSession, research_session: SessionOr404, unanswered: bool = True
) -> list[DecisionOut]:
    """Decisions raised in this session, unanswered ones by default."""
    statement = select(Decision).where(
        Decision.research_session_id == research_session.id
    )
    if unanswered:
        statement = statement.where(Decision.answer.is_(None))
    rows = db.execute(statement.order_by(Decision.id)).scalars()
    return [DecisionOut.model_validate(row) for row in rows]


@router.get("/sessions/{session_id}/operations/")
def list_operations(db: DbSession, research_session: SessionOr404) -> list[UUID]:
    """Operation ids in this session, oldest first."""
    return list(
        db.execute(
            select(Operation.id)
            .where(Operation.research_session_id == research_session.id)
            .order_by(Operation.id)
        ).scalars()
    )


@router.get("/sessions/{session_id}/artifacts/{artifact_type}/")
def get_artifact(
    db: DbSession, research_session: SessionOr404, artifact_type: str
) -> ArtifactOut:
    """The current version of one artifact — how results are read back out."""
    artifact = db.execute(
        select(CurrentArtifact)
        .where(CurrentArtifact.research_session_id == research_session.id)
        .where(CurrentArtifact.type == artifact_type)
    ).scalar_one_or_none()
    if artifact is None:
        raise HTTPException(404, f"no {artifact_type} artifact yet")
    return ArtifactOut.model_validate(artifact)
