from research_mapper.engine.context import NeedsInput


def test_needs_input_inherits_base_exception():
    """NeedsInput must inherit BaseException as ReAct interrupts Exception propagation"""
    assert issubclass(NeedsInput, BaseException) and not issubclass(
        NeedsInput, Exception
    )
