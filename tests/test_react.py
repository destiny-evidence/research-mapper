from unittest.mock import MagicMock

import dspy
import pytest

from research_mapper.modules.react import ResumableReAct
from research_mapper.models.react import Suspended


def ask_user(question: str) -> str:
    """Ask the user a question."""
    raise AssertionError("suspend_on tools must never actually be called")


def search(query: str) -> str:
    """Search for something."""
    return f"results for {query}"


def make_agent(max_iters: int = 10) -> ResumableReAct:
    return ResumableReAct(
        "query -> answer",
        tools=[ask_user, search],
        suspend_on={"ask_user"},
        max_iters=max_iters,
    )


def next_pred(
    tool_name: str, tool_args: dict, thought: str = "thinking"
) -> dspy.Prediction:
    return dspy.Prediction(
        next_thought=thought, next_tool_name=tool_name, next_tool_args=tool_args
    )


def test_constructor_rejects_unknown_suspend_on_tool():
    with pytest.raises(ValueError, match="ask_someone"):
        ResumableReAct(
            "query -> answer", tools=[ask_user, search], suspend_on={"ask_someone"}
        )


def test_finishes_normally_without_suspending():
    agent = make_agent()
    agent.react = MagicMock(return_value=next_pred("finish", {}))
    agent.extract = MagicMock(return_value=dspy.Prediction(answer="done"))

    result = agent(query="q")

    assert isinstance(result, dspy.Prediction)
    assert result.answer == "done"
    assert result.trajectory["tool_name_0"] == "finish"
    assert "observation_0" in result.trajectory


def test_non_suspend_tool_executes_and_loop_continues():
    agent = make_agent()
    agent.react = MagicMock(
        side_effect=[
            next_pred("search", {"query": "hpv"}),
            next_pred("finish", {}),
        ]
    )
    agent.extract = MagicMock(return_value=dspy.Prediction(answer="done"))

    result = agent(query="q")

    assert result.trajectory["observation_0"] == "results for hpv"
    assert result.trajectory["tool_name_1"] == "finish"


def test_suspends_on_configured_tool_without_calling_it():
    agent = make_agent()
    agent.react = MagicMock(
        return_value=next_pred("ask_user", {"question": "which scheme?"})
    )
    agent.extract = MagicMock()

    result = agent(query="q")

    assert isinstance(result, Suspended)
    assert result.idx == 0
    assert result.tool_name == "ask_user"
    assert result.tool_args == {"question": "which scheme?"}
    assert result.trajectory["tool_name_0"] == "ask_user"
    assert "observation_0" not in result.trajectory
    agent.extract.assert_not_called()


def test_resume_splices_in_the_answer_and_can_finish():
    agent = make_agent()
    agent.react = MagicMock(
        return_value=next_pred("ask_user", {"question": "which scheme?"})
    )
    suspended = agent(query="q")
    assert isinstance(suspended, Suspended)

    agent.react = MagicMock(return_value=next_pred("finish", {}))
    agent.extract = MagicMock(return_value=dspy.Prediction(answer="done"))

    result = agent.resume(
        suspended.trajectory, suspended.idx, "domain-inclusion", query="q"
    )

    assert isinstance(result, dspy.Prediction)
    assert result.trajectory["observation_0"] == "domain-inclusion"
    assert result.trajectory["tool_name_1"] == "finish"


def test_resume_can_suspend_again_for_a_second_question():
    agent = make_agent()
    agent.react = MagicMock(
        return_value=next_pred("ask_user", {"question": "which scheme?"})
    )
    first = agent(query="q")

    agent.react = MagicMock(
        return_value=next_pred("ask_user", {"question": "which concept?"})
    )
    second = agent.resume(first.trajectory, first.idx, "domain-inclusion", query="q")

    assert isinstance(second, Suspended)
    assert second.idx == 1
    assert second.trajectory["observation_0"] == "domain-inclusion"
    assert "observation_1" not in second.trajectory


def test_resume_keeps_counting_toward_the_original_max_iters():
    """A suspend-then-resume must not reset the iteration budget — resuming
    from idx 0 of a max_iters=2 run only has 1 further iteration to spend,
    same as an uninterrupted run would."""
    agent = make_agent(max_iters=2)
    agent.react = MagicMock(
        return_value=next_pred("ask_user", {"question": "which scheme?"})
    )
    suspended = agent(query="q")

    agent.react = MagicMock(
        side_effect=[
            next_pred("search", {"query": "hpv"}),
            next_pred("finish", {}),  # would only run if max_iters were reset
        ]
    )
    agent.extract = MagicMock(return_value=dspy.Prediction(answer="done"))

    result = agent.resume(suspended.trajectory, suspended.idx, "answer", query="q")

    assert isinstance(result, dspy.Prediction)
    # Only iteration idx=1 ran (the loop's ceiling), then fell through to extract.
    assert "tool_name_1" in result.trajectory
    assert "tool_name_2" not in result.trajectory
    agent.react.assert_called_once()
