from unittest.mock import MagicMock

from research_mapper.models.common import UserQuery
from research_mapper.models.react import Step
from research_mapper.models.taxonomy_search import ClarificationOptions
from research_mapper.modules.taxonomy_search import TaxonomyConceptFilterGenerator

_UNSURE = "I'm not sure / none of these"


def _step(idx: int, tool_name: str, tool_args: dict | None = None) -> Step:
    return Step(
        trajectory={f"thought_{idx}": "thinking"},
        idx=idx,
        thought="thinking",
        tool_name=tool_name,
        tool_args=tool_args or {},
    )


def _request(question: str, options: list[str]) -> dict:
    """Shaped like the raw tool_args a proposed ask_for_clarification Step
    carries — a plain dict, not yet coerced into a ClarificationOptions."""
    return {"request": {"question": question, "options": options}}


def _final(reasoning: str = "done") -> MagicMock:
    final = MagicMock()
    final.filter_groups = []
    final.reasoning = reasoning
    return final


# ---------------------------------------------------------------------------
# _prompt_clarification — moved here from ConceptFilterGenerationTools, which
# no longer exists: ask_for_clarification itself never touches the TUI now.
# ---------------------------------------------------------------------------


def test_prompt_clarification_appends_unsure_option():
    mock_ui = MagicMock()
    mock_ui.select_from_list.return_value = ["A"]
    generator = TaxonomyConceptFilterGenerator(ui=mock_ui)

    result = generator._prompt_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B"])
    )

    mock_ui.select_from_list.assert_called_once_with(["A", "B", _UNSURE], default=[3])
    assert result == ["A"]


def test_prompt_clarification_allows_unsure_alone():
    mock_ui = MagicMock()
    mock_ui.select_from_list.return_value = [_UNSURE]
    generator = TaxonomyConceptFilterGenerator(ui=mock_ui)

    result = generator._prompt_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B"])
    )

    assert result == [_UNSURE]
    assert mock_ui.select_from_list.call_count == 1


def test_prompt_clarification_rejects_unsure_combined_with_other_options():
    mock_ui = MagicMock()
    mock_ui.select_from_list.side_effect = [
        ["A", _UNSURE],  # invalid: mixed with a real option
        ["A"],  # corrected on retry
    ]
    generator = TaxonomyConceptFilterGenerator(ui=mock_ui)

    result = generator._prompt_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B"])
    )

    assert result == ["A"]
    assert mock_ui.select_from_list.call_count == 2


def test_prompt_clarification_defaults_to_the_unsure_option():
    """Pressing Enter with no thought must not silently pick the LLM's first option."""
    mock_ui = MagicMock()
    generator = TaxonomyConceptFilterGenerator(ui=mock_ui)

    generator._prompt_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B", "C"])
    )

    _, kwargs = mock_ui.select_from_list.call_args
    assert kwargs["default"] == [4]  # 1-indexed; "I'm not sure" is the 4th of 4 options


# ---------------------------------------------------------------------------
# forward — driving ResumableReAct step by step
# ---------------------------------------------------------------------------


def test_forward_drives_the_agent_step_by_step_to_completion():
    generator = TaxonomyConceptFilterGenerator()
    step0 = _step(0, "mark_unsatisfiable", {"reason": "no match"})
    generator.agent.start = MagicMock(return_value=step0)
    generator.agent.resume = MagicMock(return_value=_final())

    result = generator.forward(UserQuery(query="q"), taxonomy_concepts=[])

    generator.agent.resume.assert_called_once_with(
        step0, user_query=UserQuery(query="q"), taxonomy_concepts=[]
    )
    assert result.reasoning == "done"


def test_forward_captures_the_unsatisfiable_reason_from_the_step_args():
    """No stateful tool needed — the reason is read straight off tool_args,
    which the caller already sees before the (now-real, stateless) tool
    runs."""
    generator = TaxonomyConceptFilterGenerator()
    step0 = _step(0, "mark_unsatisfiable", {"reason": "no matching concept"})
    generator.agent.start = MagicMock(return_value=step0)
    generator.agent.resume = MagicMock(return_value=_final())

    result = generator.forward(UserQuery(query="q"), taxonomy_concepts=[])

    assert result.unsatisfiable_reason == "no matching concept"


def test_forward_reason_does_not_leak_between_calls():
    generator = TaxonomyConceptFilterGenerator()
    unsatisfiable_step = _step(0, "mark_unsatisfiable", {"reason": "no match"})
    generator.agent.start = MagicMock(return_value=unsatisfiable_step)
    generator.agent.resume = MagicMock(return_value=_final())
    first = generator.forward(UserQuery(query="q1"), taxonomy_concepts=[])
    assert first.unsatisfiable_reason == "no match"

    generator.agent.start = MagicMock(return_value=_final())
    second = generator.forward(UserQuery(query="q2"), taxonomy_concepts=[])
    assert second.unsatisfiable_reason is None


def test_forward_answers_a_clarification_step_via_the_ui_and_resumes():
    mock_ui = MagicMock()
    mock_ui.select_from_list.return_value = ["intervention"]
    generator = TaxonomyConceptFilterGenerator(ui=mock_ui)

    clarification_step = _step(
        0,
        "ask_for_clarification",
        _request("Which scheme?", ["intervention", "outcome"]),
    )
    generator.agent.start = MagicMock(return_value=clarification_step)
    generator.agent.resume = MagicMock(return_value=_final())

    generator.forward(UserQuery(query="q"), taxonomy_concepts=[])

    resumed_with = generator.agent.resume.call_args.args[0]
    assert resumed_with.trajectory["observation_0"] == ["intervention"]


def test_forward_prints_the_reasoning_behind_a_clarification_step_too():
    """The agent's thought for *why* it's asking should be visible before the
    question itself — not just skipped because the tool happens to be
    ask_for_clarification."""
    mock_ui = MagicMock()
    mock_ui.select_from_list.return_value = ["intervention"]
    generator = TaxonomyConceptFilterGenerator(ui=mock_ui)

    clarification_step = _step(
        0,
        "ask_for_clarification",
        _request("Which scheme?", ["intervention", "outcome"]),
    )
    generator.agent.start = MagicMock(return_value=clarification_step)
    generator.agent.resume = MagicMock(return_value=_final())

    generator.forward(UserQuery(query="q"), taxonomy_concepts=[])

    mock_ui.print_reasoning.assert_called_once_with("Step 0", "thinking")


def test_forward_prints_every_step_live_when_a_ui_is_given():
    mock_ui = MagicMock()
    generator = TaxonomyConceptFilterGenerator(ui=mock_ui)

    search_step = _step(0, "some_other_tool")
    generator.agent.start = MagicMock(return_value=search_step)
    generator.agent.resume = MagicMock(return_value=_final())

    generator.forward(UserQuery(query="q"), taxonomy_concepts=[])

    mock_ui.print_reasoning.assert_called_once_with("Step 0", "thinking")


def test_forward_does_not_touch_ui_when_none_is_given():
    generator = TaxonomyConceptFilterGenerator()
    step0 = _step(0, "some_other_tool")
    generator.agent.start = MagicMock(return_value=step0)
    generator.agent.resume = MagicMock(return_value=_final())

    # Would raise if forward() ever touched self.ui — there isn't one.
    generator.forward(UserQuery(query="q"), taxonomy_concepts=[])


def test_ask_for_clarification_only_registered_as_a_tool_when_ui_given():
    without_ui = TaxonomyConceptFilterGenerator()
    assert "ask_for_clarification" not in without_ui.agent.tools

    with_ui = TaxonomyConceptFilterGenerator(ui=MagicMock())
    assert "ask_for_clarification" in with_ui.agent.tools
