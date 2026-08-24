from unittest.mock import MagicMock

import dspy

from research_mapper.models.react import Step
from research_mapper.modules.react import ResumableReAct


def search(query: str) -> str:
    """Search for something."""
    return f"results for {query}"


def make_agent(max_iters: int = 10) -> ResumableReAct:
    return ResumableReAct("query -> answer", tools=[search], max_iters=max_iters)


def next_pred(
    tool_name: str, tool_args: dict, thought: str = "thinking"
) -> dspy.Prediction:
    return dspy.Prediction(
        next_thought=thought, next_tool_name=tool_name, next_tool_args=tool_args
    )


def test_start_proposes_the_first_step_without_executing_its_tool():
    agent = make_agent()
    agent.react = MagicMock(return_value=next_pred("search", {"query": "hpv"}))
    agent.tools["search"].func = MagicMock(
        side_effect=AssertionError("must not run before resume() approves it")
    )

    step = agent.start(query="q")

    assert isinstance(step, Step)
    assert step.idx == 0
    assert step.tool_name == "search"
    assert step.tool_args == {"query": "hpv"}
    assert "observation_0" not in step.trajectory


def test_resume_executes_the_approved_tool_and_proposes_the_next_step():
    agent = make_agent()
    agent.react = MagicMock(return_value=next_pred("search", {"query": "hpv"}))
    step = agent.start(query="q")

    agent.react = MagicMock(return_value=next_pred("finish", {}))
    result = agent.resume(step, query="q")

    assert isinstance(result, Step)
    assert result.idx == 1
    assert result.tool_name == "finish"
    assert result.trajectory["observation_0"] == "results for hpv"


def test_resume_on_finish_runs_it_and_returns_the_final_prediction():
    agent = make_agent()
    agent.react = MagicMock(return_value=next_pred("finish", {}))
    step = agent.start(query="q")

    agent.extract = MagicMock(return_value=dspy.Prediction(answer="done"))
    result = agent.resume(step, query="q")

    assert isinstance(result, dspy.Prediction)
    assert result.answer == "done"
    assert result.trajectory["tool_name_0"] == "finish"
    assert "observation_0" in result.trajectory


def test_forward_drives_every_step_to_completion_without_pausing():
    agent = make_agent()
    agent.react = MagicMock(
        side_effect=[
            next_pred("search", {"query": "hpv"}),
            next_pred("finish", {}),
        ]
    )
    agent.extract = MagicMock(return_value=dspy.Prediction(answer="done"))

    result = agent(query="q")

    assert isinstance(result, dspy.Prediction)
    assert result.trajectory["observation_0"] == "results for hpv"
    assert result.trajectory["tool_name_1"] == "finish"


def test_caller_can_edit_the_trajectory_before_resuming():
    """The whole point of surfacing every step: a caller can correct/rewrite
    trajectory contents before letting the run continue, with no special
    support needed beyond Step carrying a plain, mutable dict."""
    agent = make_agent()
    agent.react = MagicMock(return_value=next_pred("search", {"query": "hpv"}))
    step = agent.start(query="q")

    agent.react = MagicMock(return_value=next_pred("finish", {}))
    agent.extract = MagicMock(return_value=dspy.Prediction(answer="done"))

    edited = step.model_copy(
        update={"trajectory": {**step.trajectory, "thought_0": "corrected by caller"}}
    )
    result = agent.resume(edited, query="q")

    assert result.trajectory["thought_0"] == "corrected by caller"


def test_resume_keeps_counting_toward_the_original_max_iters():
    """Stepping through a run must not lose track of the iteration budget —
    a max_iters=2 run only ever proposes idx 0 and 1, however many times the
    caller pauses between them."""
    agent = make_agent(max_iters=2)
    agent.react = MagicMock(
        side_effect=[
            next_pred("search", {"query": "hpv"}),
            next_pred("search", {"query": "hpv again"}),
            next_pred("finish", {}),  # would only run if max_iters were exceeded
        ]
    )
    agent.extract = MagicMock(return_value=dspy.Prediction(answer="done"))

    step0 = agent.start(query="q")
    step1 = agent.resume(step0, query="q")
    assert isinstance(step1, Step)
    assert step1.idx == 1

    result = agent.resume(step1, query="q")

    assert isinstance(result, dspy.Prediction)
    assert "tool_name_2" not in result.trajectory
    assert agent.react.call_count == 2
