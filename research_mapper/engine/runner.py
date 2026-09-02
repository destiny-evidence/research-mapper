"""Operation execution."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from research_mapper.db.session import SessionFactory
from research_mapper.engine import queue, registry
from research_mapper.engine.answers import validate_answer
from research_mapper.engine.context import NeedsInput, StepContext
from research_mapper.engine.enums import OperationStatus
from research_mapper.engine.models import (
    ONE_RUNNING_PER_SESSION,
    Decision,
    Operation,
    ResearchSession,
)

logger = logging.getLogger(__name__)

ContextFactory = Callable[[str, UUID, SessionFactory], StepContext]


# A job only comes back round when pgqueuer decided the worker holding it was
# gone, so an operation already marked running is safe to take over.
CLAIMABLE = (
    OperationStatus.PENDING,
    OperationStatus.AWAITING_INPUT,
    OperationStatus.RUNNING,
)


class SessionBusy(Exception):
    """Another operation holds this session's running slot. Try again later."""


def _claim(session_factory: SessionFactory, operation_id: UUID) -> str | None:
    """Take the session's running slot, returning the workflow the session declares."""
    declared_workflow = (
        select(ResearchSession.workflow)
        .where(ResearchSession.id == Operation.research_session_id)
        .correlate(Operation)
        .scalar_subquery()
    )
    with session_factory() as db:
        try:
            claimed = db.execute(
                update(Operation)
                .where(Operation.id == operation_id)
                .where(Operation.status.in_(CLAIMABLE))
                .values(status=OperationStatus.RUNNING, error=None)
                .returning(declared_workflow)
            ).scalar_one_or_none()
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            diag = getattr(exc.orig, "diag", None)
            if getattr(diag, "constraint_name", None) != ONE_RUNNING_PER_SESSION:
                raise
            msg = f"another operation is running on {operation_id}'s session"
            raise SessionBusy(msg) from exc
    return claimed


def _finish(session_factory: SessionFactory, operation_id: UUID, result: dict) -> None:
    """Complete an operation, bumping the session version if it mutated state."""
    with session_factory() as db:
        operation = db.get(Operation, operation_id)
        if operation is None:
            msg = f"operation {operation_id} vanished before it could complete"
            raise LookupError(msg)
        operation.status = OperationStatus.COMPLETE
        operation.result = result
        if operation.mutates_state:
            operation.version_number = db.execute(
                update(ResearchSession)
                .where(ResearchSession.id == operation.research_session_id)
                .values(head_version_number=ResearchSession.head_version_number + 1)
                .returning(ResearchSession.head_version_number)
            ).scalar_one()
        db.commit()


def _block(
    session_factory: SessionFactory, operation_id: UUID, ctx: StepContext
) -> None:
    """Record the decisions a step is waiting on and park the operation."""
    with session_factory() as db:
        operation = db.get(Operation, operation_id)
        if operation is None:
            msg = f"operation {operation_id} vanished before it could block"
            raise LookupError(msg)
        existing = set(
            db.execute(
                select(Decision.key).where(Decision.operation_id == operation_id)
            ).scalars()
        )
        for key, spec in ctx.pending_decisions.items():
            if key in existing:
                continue
            db.add(
                Decision(
                    research_session_id=operation.research_session_id,
                    operation_id=operation_id,
                    type=spec.type,
                    key=key,
                    prompt=spec.prompt,
                    options=spec.options,
                    constraints=spec.constraints,
                )
            )
        operation.status = OperationStatus.AWAITING_INPUT
        db.commit()


def _fail(
    session_factory: SessionFactory, operation_id: UUID, error: Exception
) -> None:
    """Mark an operation failed and record what it raised."""
    with session_factory() as db:
        db.execute(
            update(Operation)
            .where(Operation.id == operation_id)
            .values(
                status=OperationStatus.FAILED,
                error={"type": type(error).__name__, "message": str(error)},
                attempt=Operation.attempt + 1,
            )
        )
        db.commit()


def run_operation(
    operation_id: UUID,
    session_factory: SessionFactory,
    context_factory: ContextFactory,
) -> None:
    """Run one operation to completion, to a decision, or to failure."""
    workflow = _claim(session_factory, operation_id)
    if workflow is None:
        logger.info("operation %s is not runnable, leaving it alone", operation_id)
        return
    try:
        ctx = context_factory(workflow, operation_id, session_factory)
    except Exception as exc:
        logger.exception("operation %s has no context to run in", operation_id)
        _fail(session_factory, operation_id, exc)
        raise
    try:
        step_class = registry.get(ctx.operation_type)
        result = step_class().run(ctx, step_class.Params.model_validate(ctx.params))
    except NeedsInput:
        logger.info("operation %s awaiting input", operation_id)
        _block(session_factory, operation_id, ctx)
    except Exception as exc:
        logger.exception("operation %s failed", operation_id)
        _fail(session_factory, operation_id, exc)
        raise
    else:
        _finish(session_factory, operation_id, result)


def create_operation(
    research_session_id: UUID,
    created_by_id: UUID,
    operation_type: str,
    params: dict,
    session_factory: SessionFactory,
) -> UUID:
    """Validate, record and queue a new operation."""
    step_class = registry.get(operation_type)
    validated = step_class.Params.model_validate(params)
    with session_factory() as db:
        # Running a step again abandons an earlier attempt still holding a
        # question, so it stops reading as live work.
        db.execute(
            update(Operation)
            .where(Operation.research_session_id == research_session_id)
            .where(Operation.type == operation_type)
            .where(Operation.status == OperationStatus.AWAITING_INPUT)
            .values(status=OperationStatus.SUPERSEDED)
        )
        operation = Operation(
            research_session_id=research_session_id,
            created_by_id=created_by_id,
            type=operation_type,
            params=validated.model_dump(mode="json"),
            mutates_state=step_class.mutates_state,
        )
        db.add(operation)
        db.flush()
        queue.enqueue_in(db, operation.id)
        db.commit()
    return operation.id


def answer_decisions(
    operation_id: UUID,
    answers: dict[str, list[dict]],
    session_factory: SessionFactory,
) -> UUID | None:
    """Answer an operation's decisions in one go, requeueing it when none remain open."""
    if not answers:
        msg = "no answers given"
        raise LookupError(msg)
    with session_factory() as db:
        open_decisions = {
            decision.key: decision
            for decision in db.execute(
                select(Decision)
                .where(Decision.operation_id == operation_id)
                .where(Decision.answer.is_(None))
                # Two callers each answering part of the set must not both
                # conclude the other's questions are still open and leave the
                # operation parked with nothing left to answer.
                .with_for_update()
            ).scalars()
        }
        if unknown := answers.keys() - open_decisions.keys():
            msg = f"no open decision for {sorted(unknown)}"
            raise LookupError(msg)
        for key, answer in answers.items():
            validate_answer(open_decisions[key], answer)
        answered_at = datetime.now(UTC)
        for key, answer in answers.items():
            open_decisions[key].answer = answer
            open_decisions[key].answered_at = answered_at
        resumed = None
        if not open_decisions.keys() - answers.keys():
            resumed = db.execute(
                update(Operation)
                .where(Operation.id == operation_id)
                .where(Operation.status == OperationStatus.AWAITING_INPUT)
                .values(status=OperationStatus.PENDING)
                .returning(Operation.id)
            ).scalar_one_or_none()
            if resumed:
                queue.enqueue_in(db, resumed)
        db.commit()
    return resumed


def retry_operation(operation_id: UUID, session_factory: SessionFactory) -> None:
    """Put a failed operation back on the queue."""
    with session_factory() as db:
        requeued = db.execute(
            update(Operation)
            .where(Operation.id == operation_id)
            .where(Operation.status == OperationStatus.FAILED)
            .values(status=OperationStatus.PENDING)
            .returning(Operation.id)
        ).scalar_one_or_none()
        if requeued is None:
            operation = db.get(Operation, operation_id)
            if operation is None:
                msg = f"no operation {operation_id}"
                raise LookupError(msg)
            msg = f"operation {operation_id} is {operation.status}, not failed"
            raise ValueError(msg)
        queue.enqueue_in(db, operation_id)
        db.commit()
