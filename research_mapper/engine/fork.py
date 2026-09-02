"""Copying a session up to one of its questions."""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_mapper.engine import queue
from research_mapper.engine.enums import OperationStatus
from research_mapper.engine.models import Artifact, Decision, Operation, ResearchSession
from research_mapper.engine.runner import SessionBusy
from research_mapper.engine.views import Progress

BUSY = (OperationStatus.PENDING, OperationStatus.RUNNING)
FRESH = frozenset({"id", "created_at", "updated_at"})


@dataclass(frozen=True)
class Cut:
    """Where a fork was taken, for a workflow copying its own tables."""

    source_id: UUID
    new_id: UUID
    operation_types: frozenset[str]


StateFactory = Callable[[str, Session, Cut], None]


def _clone(row, **changes):
    values = {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.name not in FRESH
    }
    return type(row)(id=uuid7(), **values | changes)


def _written(db, decisions, artifacts) -> list:
    """The matching decisions and artifacts, in the order they were written.

    Cloning in this order is what lets a fork of a fork still date a question
    against the checkpoints it was asked over: uuid7 is monotonic, so copies come
    out in the same order as the rows they came from.
    """
    return sorted(
        [
            *db.execute(select(Decision).where(decisions)).scalars(),
            *db.execute(select(Artifact).where(artifacts)).scalars(),
        ],
        key=lambda row: row.id,
    )


def fork(
    db: Session,
    source: ResearchSession,
    user_id: UUID,
    reopen_decision: UUID,
    state_factory: StateFactory | None = None,
) -> ResearchSession:
    """Copy a session up to one of its questions, and ask that question again."""
    if db.execute(
        select(Operation.id)
        .where(Operation.research_session_id == source.id)
        .where(Operation.status.in_(BUSY))
    ).first():
        msg = "this session has work in flight"
        raise SessionBusy(msg)

    decision = db.get(Decision, reopen_decision)
    if decision is None or decision.research_session_id != source.id:
        msg = f"no decision {reopen_decision} in this session"
        raise LookupError(msg)
    reopened = db.get(Operation, decision.operation_id)
    if reopened is None:
        msg = f"decision {reopen_decision} belongs to no operation"
        raise LookupError(msg)

    # Everything finished that the reopened operation was started after. Its own
    # version number is the tighter bound where it has one; an abandoned attempt
    # never gets one, and has newer work behind it. An earlier attempt at the step
    # being reopened is not prefix: the fork is redoing it.
    prefix = (
        select(Operation)
        .where(Operation.research_session_id == source.id)
        .where(Operation.version_number.is_not(None))
        .where(Operation.id < reopened.id)
        .where(Operation.type != reopened.type)
    )
    if reopened.version_number is not None:
        prefix = prefix.where(Operation.version_number < reopened.version_number)
    operations = db.execute(prefix.order_by(Operation.id)).scalars().all()

    head = max((operation.version_number or 0 for operation in operations), default=0)
    forked = ResearchSession(
        user_id=user_id,
        workflow=source.workflow,
        workflow_version=source.workflow_version,
        question=source.question,
        community=source.community,
        params=source.params,
        head_version_number=head,
        forked_from_id=source.id,
        forked_at_step=reopened.type,
    )
    db.add(forked)
    db.flush()

    copied = {}
    for operation in operations:
        clone = _clone(operation, research_session_id=forked.id)
        copied[operation.id] = clone.id
        db.add(clone)

    if copied:
        for row in _written(
            db,
            Decision.operation_id.in_(list(copied)),
            Artifact.operation_id.in_(list(copied)),
        ):
            db.add(
                _clone(
                    row,
                    research_session_id=forked.id,
                    operation_id=copied[row.operation_id],
                )
            )

    clone = _clone(
        reopened,
        research_session_id=forked.id,
        created_by_id=user_id,
        # Defaults, not the parent's: a fork exists to re-ask against the
        # checkpoint it carries, and params like regenerate mean discard it.
        params={},
        status=OperationStatus.PENDING,
        version_number=None,
        result=None,
        error=None,
        attempt=0,
        progress=Progress(),
    )
    db.add(clone)

    # The settled questions before this one, and only what the step had
    # checkpointed before it asked it: no later pause's suggestion, and not the
    # answer being dropped.
    for row in _written(
        db,
        (Decision.operation_id == reopened.id)
        & (Decision.id < decision.id)
        & Decision.answer.is_not(None),
        (Artifact.operation_id == reopened.id) & (Artifact.id < decision.id),
    ):
        db.add(_clone(row, research_session_id=forked.id, operation_id=clone.id))
    queue.enqueue_in(db, clone.id)

    if state_factory is not None:
        types = frozenset(operation.type for operation in operations)
        state_factory(source.workflow, db, Cut(source.id, forked.id, types))

    db.commit()
    return forked
