import logging
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select, update

from research_mapper.db.session import SessionFactory
from research_mapper.workflow import registry
from research_mapper.workflow.context import NeedsInput, StepContext
from research_mapper.workflow.enums import OperationStatus
from research_mapper.workflow.models import Decision, Operation, ResearchSession

logger = logging.getLogger(__name__)

ContextFactory = Callable[[UUID, SessionFactory], StepContext]


def _mark_running(session_factory: SessionFactory, operation_id: UUID) -> None:
    """Move an operation into the running state."""
    with session_factory() as db:
        db.execute(
            update(Operation)
            .where(Operation.id == operation_id)
            .values(status=OperationStatus.RUNNING)
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


def _fail(session_factory: SessionFactory, operation_id: UUID, error: str) -> None:
    """Mark an operation failed and record why."""
    with session_factory() as db:
        db.execute(
            update(Operation)
            .where(Operation.id == operation_id)
            .values(
                status=OperationStatus.FAILED,
                error={"message": error},
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
    step_class = registry.get(ctx.operation_type)
    step = step_class()
    try:
        result = step.run(ctx, step_class.Params.model_validate(ctx.params))
    except NeedsInput:
        logger.info("operation %s awaiting input", operation_id)
        _block(session_factory, operation_id, ctx)
    except Exception:
        logger.exception("operation %s failed", operation_id)
        _fail(session_factory, operation_id, "step raised")
        raise
    else:
        _finish(session_factory, operation_id, result)
