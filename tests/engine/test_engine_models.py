import pytest
from sqlalchemy.exc import IntegrityError

from factories import make_operation, make_session, make_user
from research_mapper.engine.enums import DecisionType, OperationStatus
from research_mapper.engine.models import Decision


def test_ids_and_timestamps_are_filled_in_and_ordered(db):
    first = make_user(db, "a")
    second = make_user(db, "b")

    assert first.created_at is not None
    assert first.id < second.id, "uuid7 should sort by creation time"


def test_only_one_operation_may_run_per_session(db):
    user = make_user(db)
    session = make_session(db, user)
    make_operation(db, session, user, status=OperationStatus.RUNNING)

    with pytest.raises(IntegrityError):
        make_operation(db, session, user, status=OperationStatus.RUNNING)


def test_a_second_session_may_run_at_the_same_time(db):
    user = make_user(db)
    make_operation(db, make_session(db, user), user, status=OperationStatus.RUNNING)
    make_operation(db, make_session(db, user), user, status=OperationStatus.RUNNING)


def test_version_numbers_are_unique_within_a_session(db):
    user = make_user(db)
    session = make_session(db, user)
    make_operation(db, session, user, version_number=1)
    make_operation(db, session, user, version_number=None)
    make_operation(db, session, user, version_number=None)

    with pytest.raises(IntegrityError):
        make_operation(db, session, user, version_number=1)


def add_decision(db, session, operation, key, answer=None):
    db.add(
        Decision(
            research_session_id=session.id,
            operation_id=operation.id,
            type=DecisionType.SELECT_MANY,
            key=key,
            prompt="pick",
            answer=answer,
        )
    )
    db.commit()


def test_a_decision_key_is_unique_within_an_operation(db):
    user = make_user(db)
    session = make_session(db, user)
    operation = make_operation(db, session, user)
    add_decision(db, session, operation, "pick_queries")

    with pytest.raises(IntegrityError):
        add_decision(db, session, operation, "pick_queries")


def test_a_session_may_have_several_open_decisions(db):
    """ask_all needs this; the index over pending decisions must not be unique."""
    user = make_user(db)
    session = make_session(db, user)
    operation = make_operation(db, session, user)
    add_decision(db, session, operation, "pick_queries")
    add_decision(db, session, operation, "pick_filters")

    assert db.query(Decision).count() == 2
