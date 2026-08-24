import asyncio
import uuid

from research_mapper.engine import queue


def test_enqueue_hands_the_operation_id_to_the_worker(queued):
    operation_id = uuid.uuid4()
    asyncio.run(queue.enqueue(operation_id))

    assert queued() == [str(operation_id)]
