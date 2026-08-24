import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update

from research_mapper.db.session import SessionFactory
from research_mapper.engine import queue, registry
from research_mapper.engine.answers import validate_answer
from research_mapper.engine.context import NeedsInput, StepContext
from research_mapper.engine.enums import OperationStatus
from research_mapper.engine.models import Decision, Operation, ResearchSession

logger = logging.getLogger(__name__)

ContextFactory = Callable[[UUID, SessionFactory], StepContext]


def _mark_running(session_factory: SessionFactory, operation_id: UUID) -> None:
    """Move an operation into the running state, clearing the last attempt's error."""
    with session_factory() as db:
        db.execute(
            update(Operation)
            .where(Operation.id == operation_id)
            .values(status=OperationStatus.RUNNING, error=None)
        )
        db.commit()


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
    _mark_running(session_factory, operation_id)
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
        db.commit()
    queue.enqueue_sync(operation.id)
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
        db.commit()
    if resumed:
        queue.enqueue_sync(resumed)
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
        db.commit()
    queue.enqueue_sync(operation_id)
