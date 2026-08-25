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
from research_mapper.engine.models import Decision, Operation, ResearchSession

logger = logging.getLogger(__name__)

ContextFactory = Callable[[UUID, SessionFactory], StepContext]


# A job only comes back round when pgqueuer decided the worker holding it was
# gone, so an operation already marked running is safe to take over.
CLAIMABLE = (
    OperationStatus.PENDING,
    OperationStatus.AWAITING_INPUT,
    OperationStatus.RUNNING,
)


class SessionBusy(Exception):
    """Another operation holds this session's running slot. Try again later."""


def _claim(session_factory: SessionFactory, operation_id: UUID) -> bool:
    with session_factory() as db:
        try:
            claimed = db.execute(
                update(Operation)
                .where(Operation.id == operation_id)
                .where(Operation.status.in_(CLAIMABLE))
                .values(status=OperationStatus.RUNNING, error=None)
                .returning(Operation.id)
            ).scalar_one_or_none()
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            msg = f"another operation is running on {operation_id}'s session"
            raise SessionBusy(msg) from exc
    return claimed is not None


def _finish(session_factory: SessionFactory, operation_id: UUID, result: dict) -> None:
    """Complete an operation, bumping the session version if it mutated state."""
    with session_factory() as db:
        operation = db.get(Operation, operation_id)
        if operation is None:
            msg = f"operation {operation_id} vanished before it could complete"
            raise LookupError(msg)
        values: dict = {"status": OperationStatus.COMPLETE, "result": result}
        if operation.mutates_state:
            research_session = db.get(
                ResearchSession, operation.research_session_id, with_for_update=True
            )
            if research_session is None:
                msg = f"session {operation.research_session_id} vanished"
                raise LookupError(msg)
            research_session.head_version_number += 1
            values["version_number"] = research_session.head_version_number
        db.execute(
            update(Operation).where(Operation.id == operation_id).values(**values)
        )
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
        db.execute(
            update(Operation)
            .where(Operation.id == operation_id)
            .values(status=OperationStatus.AWAITING_INPUT)
        )
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
    if not _claim(session_factory, operation_id):
        logger.info("operation %s is not runnable, leaving it alone", operation_id)
        return
    ctx = context_factory(operation_id, session_factory)
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
