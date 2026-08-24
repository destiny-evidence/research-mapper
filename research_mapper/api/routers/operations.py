from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from research_mapper.api.deps import DbSession, Factory
from research_mapper.api.schemas import DecisionOut, OperationOut, Respond
from research_mapper.engine import runner
from research_mapper.engine.answers import InvalidAnswer
from research_mapper.engine.models import Decision, Operation
from sqlalchemy.orm import Session

router = APIRouter(prefix="/operations", tags=["operations"])


def _load(db: Session, operation_id: UUID) -> Operation:
    operation = db.get(Operation, operation_id)
    if operation is None:
        raise HTTPException(404, "operation not found")
    return operation


def _out(db: Session, operation: Operation) -> OperationOut:
    """Shape an operation."""
    db.refresh(operation)
    decisions = [
        DecisionOut.model_validate(row)
        for row in db.execute(
            select(Decision)
            .where(Decision.operation_id == operation.id)
            .order_by(Decision.id)
        ).scalars()
    ]
    open_decisions = [row for row in decisions if row.answer is None]
    return OperationOut(
        **{
            field: getattr(operation, field)
            for field in OperationOut.model_fields
            if field not in ("pending_question", "decisions")
        },
        pending_question=open_decisions[0] if len(open_decisions) == 1 else None,
        decisions=decisions,
    )


@router.get("/{operation_id}/")
def read_operation(db: DbSession, operation_id: UUID) -> OperationOut:
    """Get an operation."""
    return _out(db, _load(db, operation_id))


@router.post("/{operation_id}/respond/")
def respond(
    body: Respond, db: DbSession, operation_id: UUID, session_factory: Factory
) -> OperationOut:
    """Answer one or several of an operation's open decisions, keyed by decision key."""
    operation = _load(db, operation_id)
    try:
        runner.answer_decisions(operation.id, body.answers, session_factory)
    except LookupError as exc:
        raise HTTPException(400, str(exc)) from exc
    except InvalidAnswer as exc:
        raise HTTPException(422, str(exc)) from exc
    return _out(db, operation)


@router.post("/{operation_id}/retry/")
def retry(db: DbSession, operation_id: UUID, session_factory: Factory) -> OperationOut:
    """Requeue a failed operation."""
    operation = _load(db, operation_id)
    try:
        runner.retry_operation(operation.id, session_factory)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _out(db, operation)
