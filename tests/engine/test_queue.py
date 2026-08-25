import uuid

from research_mapper.engine import queue


def test_enqueue_hands_the_operation_id_to_the_worker(database, queued):
    operation_id = uuid.uuid4()
    with database() as db:
        queue.enqueue_in(db, operation_id)
        db.commit()

    assert queued() == [str(operation_id)]


def test_a_rolled_back_operation_is_never_queued(database, queued):
    """The job and the operation row land together or not at all."""
    with database() as db:
        queue.enqueue_in(db, uuid.uuid4())
        db.rollback()

    assert queued() == []
