import asyncio
import uuid

import pytest
from sqlalchemy import text

from research_mapper.engine import queue


@pytest.fixture
def queued(database):
    """Empty the queue and yield a reader over it."""
    with database() as db:
        db.execute(text("TRUNCATE pgqueuer"))
        db.commit()

    def read() -> list[tuple[str, str]]:
        with database() as db:
            return [
                (row.entrypoint, bytes(row.payload).decode())
                for row in db.execute(
                    text("SELECT entrypoint, payload FROM pgqueuer")
                ).all()
            ]

    return read


def test_enqueue_hands_the_operation_id_to_the_worker(queued):
    operation_id = uuid.uuid4()
    asyncio.run(queue.enqueue(operation_id))

    assert queued() == [(queue.ENTRYPOINT, str(operation_id))]


def test_enqueueing_twice_leaves_one_job(queued):
    """A user clicking twice must not run the operation twice."""
    operation_id = uuid.uuid4()
    asyncio.run(queue.enqueue(operation_id))
    asyncio.run(queue.enqueue(operation_id))

    assert len(queued()) == 1
