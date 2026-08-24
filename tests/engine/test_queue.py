import asyncio
import uuid

from research_mapper.engine import queue


def test_enqueue_hands_the_operation_id_to_the_worker(queued):
    operation_id = uuid.uuid4()
    asyncio.run(queue.enqueue(operation_id))

    assert queued() == [str(operation_id)]


def test_enqueueing_twice_leaves_one_job(queued):
    """A user clicking twice must not run the operation twice."""
    operation_id = uuid.uuid4()
    asyncio.run(queue.enqueue(operation_id))
    asyncio.run(queue.enqueue(operation_id))

    assert len(queued()) == 1
