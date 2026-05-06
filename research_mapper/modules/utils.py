import asyncio
from asyncio import Semaphore
from typing import Callable, Any

import dspy


# TODO maybe add some validation that the module has a reasoning field and its signature inputs are valid
def read_reasoning_stream(
    program: dspy.Module, on_chunk: Callable[[str, bool], Any], **program_inputs
) -> dspy.Prediction:
    reasoning_listener = dspy.streaming.StreamListener(signature_field_name="reasoning")
    stream_predict = dspy.streamify(
        program, stream_listeners=[reasoning_listener], async_streaming=False
    )
    output_stream = stream_predict(**program_inputs)

    return_value = None
    for chunk in output_stream:
        if isinstance(chunk, dspy.streaming.StreamResponse):
            on_chunk(chunk.chunk)
        elif isinstance(chunk, dspy.Prediction):
            # signals to callback that stream processing has completed (i.e. there are no more chunks)
            on_chunk("", True)
            return_value = chunk
    if return_value is None:
        raise ValueError("No Prediction chunk reached")
    return return_value


# TODO probably make this configurable
SEMAPHORE = Semaphore(8)  # max 8 concurrent threads


async def run_with_semaphore(
    fn, semaphore: Semaphore = SEMAPHORE, *args, **kwargs
) -> Any:
    async with semaphore:
        return await asyncio.to_thread(fn, *args, **kwargs)
