import json
from unittest.mock import MagicMock

import dspy
from dspy.adapters.types.tool import ToolCalls
from dspy.utils.dummies import DummyLM

from research_mapper.models.react import Step
from research_mapper.modules.common import ResumableModule
from research_mapper.modules.react import ResumableReAct, reasoning_from_history


def search(query: str) -> str:
    """Search for something."""
    return f"results for {query}"


def make_agent(max_iters: int = 10) -> ResumableReAct:
    return ResumableReAct("query -> answer", tools=[search], max_iters=max_iters)


def next_pred(*calls: tuple[str, dict], thought: str = "thinking") -> dspy.Prediction:
    """One model turn, proposing `calls` as (tool name, args) pairs."""
    return dspy.Prediction(
        next_thought=thought,
        tool_calls=ToolCalls(
            tool_calls=[
                ToolCalls.ToolCall(name=name, args=args) for name, args in calls
            ]
        ),
    )


def history_of(react: MagicMock, call: int = -1) -> dspy.History:
    return react.call_args_list[call].kwargs["history"]


def test_resumable_react_satisfies_the_resumable_module_protocol():
    """ResumableReAct is the reference implementation the ResumableModule
    Protocol was written to describe — any higher-level module wrapping one
    (e.g. TaxonomyConceptFilterGenerator) should satisfy it the same way,
    structurally, with no shared base class needed."""
    assert isinstance(make_agent(), ResumableModule)


def test_classify_step_always_returns_none():
    """A bare ResumableReAct has no domain-specific pause categories of its
    own — every Step it surfaces just means "call resume() again"."""
    agent = make_agent()
    step = Step(
        trajectory={}, idx=0, thought="t", tool_name="search", tool_args={"query": "x"}
    )

    assert agent.classify_step(step) is None


def test_the_dspy_react_contract_it_builds_on():
    """ResumableReAct drives dspy.ReAct's own predictor and submit tool, and two of
    its private helpers. A dspy upgrade that changes any of these fails here."""
    agent = make_agent()

    assert set(agent.react.signature.input_fields) >= {
        "history",
        "tools",
        "turn_budget",
    }
    assert set(agent.react.signature.output_fields) == {"next_thought", "tool_calls"}
    assert "submit" in agent.tools
    assert callable(agent._turn_budget_inputs)
    assert callable(agent._forced_submit)


def test_start_proposes_the_first_step_without_executing_its_tool():
    agent = make_agent()
    agent.react = MagicMock(return_value=next_pred(("search", {"query": "hpv"})))
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
    agent.react = MagicMock(return_value=next_pred(("search", {"query": "hpv"})))
    step = agent.start(query="q")

    agent.react = MagicMock(return_value=next_pred(("submit", {"answer": "done"})))
    result = agent.resume(step, query="q")

    assert isinstance(result, Step)
    assert result.idx == 1
    assert result.tool_name == "submit"
    assert result.trajectory["observation_0"] == "results for hpv"


def test_resume_on_submit_runs_it_and_returns_the_final_prediction():
    agent = make_agent()
    agent.react = MagicMock(
        return_value=next_pred(("submit", {"answer": "done"}), thought="All found.")
    )
    step = agent.start(query="q")

    result = agent.resume(step, query="q")

    assert isinstance(result, dspy.Prediction)
    assert result.answer == "done"
    assert result.reasoning == "1. All found."
    assert result.trajectory["tool_name_0"] == "submit"
    assert "observation_0" in result.trajectory


def test_a_submit_missing_an_output_is_an_error_the_agent_sees():
    agent = make_agent()
    agent.react = MagicMock(return_value=next_pred(("submit", {})))
    step = agent.start(query="q")

    agent.react = MagicMock(return_value=next_pred(("submit", {"answer": "done"})))
    result = agent.resume(step, query="q")

    assert isinstance(result, Step), "the run goes on, so the agent can correct it"
    assert result.trajectory["error_0"] is True
    assert "answer" in result.trajectory["observation_0"]
    assert history_of(agent.react).messages[0]["tool_calls"].tool_call_results


def test_forward_drives_every_step_to_completion_without_pausing():
    agent = make_agent()
    agent.react = MagicMock(
        side_effect=[
            next_pred(("search", {"query": "hpv"})),
            next_pred(("submit", {"answer": "done"})),
        ]
    )

    result = agent(query="q")

    assert isinstance(result, dspy.Prediction)
    assert result.answer == "done"
    assert result.trajectory["observation_0"] == "results for hpv"
    assert result.trajectory["tool_name_1"] == "submit"


def test_caller_can_edit_the_trajectory_before_resuming():
    """The whole point of surfacing every step: a caller can correct/rewrite
    trajectory contents before letting the run continue, with no special
    support needed beyond Step carrying a plain, mutable dict."""
    agent = make_agent()
    agent.react = MagicMock(return_value=next_pred(("search", {"query": "hpv"})))
    step = agent.start(query="q")

    agent.react = MagicMock(return_value=next_pred(("submit", {"answer": "done"})))
    edited = step.model_copy(
        update={"trajectory": {**step.trajectory, "thought_0": "corrected by caller"}}
    )
    result = agent.resume(edited, query="q")

    assert result.trajectory["thought_0"] == "corrected by caller"
    assert history_of(agent.react).messages[0]["next_thought"] == "corrected by caller"


def test_calls_proposed_in_one_turn_are_queued_as_separate_steps():
    agent = make_agent()
    agent.react = MagicMock(
        return_value=next_pred(("search", {"query": "a"}), ("search", {"query": "b"}))
    )
    first = agent.start(query="q")

    second = agent.resume(first, query="q")

    assert (first.idx, first.tool_args) == (0, {"query": "a"})
    assert (second.idx, second.tool_args) == (1, {"query": "b"})
    assert second.trajectory["observation_0"] == "results for a"
    assert agent.react.call_count == 1, "the queued call needs no model turn"


def test_the_next_turn_sees_a_turns_calls_together_with_their_results():
    agent = make_agent()
    agent.react = MagicMock(
        side_effect=[
            next_pred(("search", {"query": "a"}), ("search", {"query": "b"})),
            next_pred(("submit", {"answer": "done"})),
        ]
    )

    agent(query="q")

    (event,) = history_of(agent.react).messages
    assert event["query"] == "q", "the inputs ride on the first event"
    assert [call.name for call in event["tool_calls"].tool_calls] == [
        "search",
        "search",
    ]
    assert [
        result.value
        for result in event["tool_calls"].tool_call_results.tool_call_results
    ] == ["results for a", "results for b"]


def test_a_clarification_queued_behind_a_lookup_pauses_at_its_own_step():
    """The caller answers it with with_observation, so the tool itself never runs."""

    def clarify(question: str) -> str:
        """Ask the human."""
        raise AssertionError("the caller answers this, it must never run")

    agent = ResumableReAct("query -> answer", tools=[search, clarify], max_iters=5)
    agent.react = MagicMock(
        side_effect=[
            next_pred(("search", {"query": "a"}), ("clarify", {"question": "which?"})),
            next_pred(("submit", {"answer": "done"})),
        ]
    )
    lookup = agent.start(query="q")
    question = agent.resume(lookup, query="q")

    assert question.tool_name == "clarify"
    answered = agent.resume(question.with_observation("regional"), query="q")

    assert answered.tool_name == "submit"
    assert answered.trajectory["observation_1"] == "regional"


def test_reasoning_joins_each_turns_thought_once():
    agent = make_agent()
    agent.react = MagicMock(
        side_effect=[
            next_pred(
                ("search", {"query": "a"}), ("search", {"query": "b"}), thought="Look."
            ),
            next_pred(("submit", {"answer": "done"}), thought="Answer."),
        ]
    )

    assert agent(query="q").reasoning == "1. Look.\n2. Answer."


def test_a_trajectory_saved_before_turns_held_several_calls_resumes():
    """Paused runs persisted by the old ReAct have no turn markers: each call was
    its own turn. They must still resume after a deploy."""
    legacy = {
        "thought_0": "Search first.",
        "tool_name_0": "search",
        "tool_args_0": {"query": "a"},
        "observation_0": "results for a",
        "thought_1": "Search again.",
        "tool_name_1": "search",
        "tool_args_1": {"query": "b"},
    }
    step = Step(
        trajectory=legacy,
        idx=1,
        thought="Search again.",
        tool_name="search",
        tool_args={"query": "b"},
    )
    agent = make_agent()
    agent.react = MagicMock(return_value=next_pred(("submit", {"answer": "done"})))

    result = agent.resume(step, query="q")

    assert result.tool_name == "submit"
    assert result.trajectory["turn_2"] == 2
    assert len(history_of(agent.react).messages) == 2


def test_a_failed_tool_is_recorded_as_an_error():
    def broken(query: str) -> str:
        """Always fails."""
        raise RuntimeError("down")

    agent = ResumableReAct("query -> answer", tools=[broken], max_iters=5)
    agent.react = MagicMock(
        side_effect=[
            next_pred(("broken", {"query": "a"})),
            next_pred(("submit", {"answer": "done"})),
        ]
    )

    result = agent(query="q")

    assert result.trajectory["error_0"] is True
    assert "Execution error in broken" in result.trajectory["observation_0"]
    (event,) = history_of(agent.react).messages
    assert event["tool_calls"].tool_call_results.tool_call_results[0].is_error


def test_the_turn_budget_running_out_forces_a_submit():
    """Stepping through a run must not lose track of the budget: with max_iters=2
    there are two turns, then dspy.ReAct's forced submit, however many times the
    caller pauses between them."""
    agent = make_agent(max_iters=2)
    agent.react = MagicMock(
        side_effect=[
            next_pred(("search", {"query": "hpv"})),
            next_pred(("search", {"query": "hpv again"})),
            next_pred(("submit", {"answer": "done"}), thought="Out of turns."),
        ]
    )

    step0 = agent.start(query="q")
    step1 = agent.resume(step0, query="q")
    assert isinstance(step1, Step)
    assert step1.idx == 1

    result = agent.resume(step1, query="q")

    assert isinstance(result, dspy.Prediction)
    assert result.answer == "done"
    assert agent.react.call_count == 3
    forced = agent.react.call_args_list[-1].kwargs["config"]["tool_choice"]
    assert forced["function"]["name"] == "submit"
    assert result.reasoning.endswith("3. Out of turns.")


def _script() -> list[dict]:
    def tool_calls(*calls):
        return {"tool_calls": [{"name": name, "args": args} for name, args in calls]}

    return [
        {
            "next_thought": "Search twice.",
            "tool_calls": tool_calls(
                ("search", {"query": "a"}), ("search", {"query": "b"})
            ),
        },
        {
            "next_thought": "Once more.",
            "tool_calls": tool_calls(("search", {"query": "c"})),
        },
        {
            "next_thought": "Done.",
            "tool_calls": tool_calls(("submit", {"answer": "A"})),
        },
    ]


def test_every_prompt_matches_dspy_reacts_own():
    """Rebuilding history from the trajectory must send the model exactly what
    dspy.ReAct's own loop would, multi-call turns included."""
    ours, theirs = DummyLM(_script()), DummyLM(_script())
    with dspy.context(lm=ours):
        make_agent(max_iters=5)(query="q")
    with dspy.context(lm=theirs):
        dspy.ReAct("query -> answer", tools=[search], max_iters=5)(query="q")

    assert len(ours.history) == len(theirs.history) == 3
    for mine, reference in zip(ours.history, theirs.history, strict=True):
        assert json.dumps(mine["messages"], default=str) == json.dumps(
            reference["messages"], default=str
        )


def test_reasoning_from_history_numbers_a_plain_react_runs_thoughts():
    """dspy.ReAct no longer returns reasoning; the subagents rebuild it from history."""
    with dspy.context(lm=DummyLM(_script())):
        prediction = dspy.ReAct("query -> answer", tools=[search], max_iters=5)(
            query="q"
        )

    assert reasoning_from_history(prediction.history) == (
        "1. Search twice.\n2. Once more.\n3. Done."
    )
    assert reasoning_from_history(None) == ""
