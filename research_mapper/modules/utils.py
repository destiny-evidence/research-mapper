import asyncio
from asyncio import Semaphore
from typing import Callable, Any

import dspy


# TODO maybe add some validation that the module has a reasoning field and its signature inputs are valid
def read_reasoning_stream(
    program: dspy.Module, on_chunk: Callable[[str, bool], Any], **program_inputs
) -> dspy.Prediction:
    """
    Wraps and runs a DSPy program to stream the generation of certain signature fields (i.e. 'reasoning' in ChainOfThought)
    :param program: the DSPy program to wrap and stream responses for
    :param on_chunk: the callback to call when a chunk is streamed
    :param program_inputs: the arguments to be forwarded to the DSPy program being wrapped
    :return:
    """
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
SEMAPHORE: Semaphore = Semaphore(8)  # max 8 concurrent threads


async def run_with_semaphore(
    fn: Callable[..., Any], semaphore: Semaphore = SEMAPHORE, *args, **kwargs
) -> Any:
    """
    Runs a process in a thread inside a semaphore.
    :param fn: the function/process to run
    :param semaphore: the semaphore to manage the execution of the function in a thread
    :param args: the arguments to be forwarded to the function to run
    :param kwargs: the keyword arguments to be forwarded to the function to run
    :return: whatever the function to run returns
    """
    async with semaphore:
        return await asyncio.to_thread(fn, *args, **kwargs)
