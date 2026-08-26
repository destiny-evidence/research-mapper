from unittest.mock import MagicMock

from research_mapper.models.common import UserQuery
from research_mapper.models.react import Step
from research_mapper.models.taxonomy_search import ClarificationOptions, IndexedVocab
from research_mapper.modules.taxonomy_search import TaxonomyConceptFilterGenerator

_NOT_SURE = "I'm not sure"
_NONE_OF_THESE = "None of these"


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


def _generator_with_mock_agent(
    ui: MagicMock | None = None, *, start_returns, resume_returns=None
) -> TaxonomyConceptFilterGenerator:
    """A generator whose _build_agent is stubbed to return a mock agent — the
    real agent now depends on per-call indexed/graph (bound taxonomy-browsing
    tools), so it can no longer just be swapped in after construction."""
    generator = TaxonomyConceptFilterGenerator(ui=ui)
    mock_agent = MagicMock()
    mock_agent.start = MagicMock(return_value=start_returns)
    mock_agent.resume = MagicMock(return_value=resume_returns or _final())
    generator._build_agent = MagicMock(return_value=mock_agent)
    return generator


def _forward(generator: TaxonomyConceptFilterGenerator, query: str = "q"):
    return generator.forward(
        UserQuery(query=query), indexed=MagicMock(), graph=MagicMock()
    )


# ---------------------------------------------------------------------------
# _prompt_clarification — moved here from ConceptFilterGenerationTools, which
# no longer exists: ask_for_clarification itself never touches the TUI now.
# ---------------------------------------------------------------------------


def test_prompt_clarification_appends_none_of_these_and_not_sure_options():
    mock_ui = MagicMock()
    mock_ui.select_from_list.return_value = ["A"]
    generator = TaxonomyConceptFilterGenerator(ui=mock_ui)

    result = generator._prompt_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B"])
    )

    mock_ui.select_from_list.assert_called_once_with(
        ["A", "B", _NONE_OF_THESE, _NOT_SURE], default=[4]
    )
    assert result == ["A"]


def test_prompt_clarification_allows_not_sure_alone():
    mock_ui = MagicMock()
    mock_ui.select_from_list.return_value = [_NOT_SURE]
    generator = TaxonomyConceptFilterGenerator(ui=mock_ui)

    result = generator._prompt_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B"])
    )

    assert result == [_NOT_SURE]
    assert mock_ui.select_from_list.call_count == 1


def test_prompt_clarification_allows_none_of_these_alone():
    mock_ui = MagicMock()
    mock_ui.select_from_list.return_value = [_NONE_OF_THESE]
    generator = TaxonomyConceptFilterGenerator(ui=mock_ui)

    result = generator._prompt_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B"])
    )

    assert result == [_NONE_OF_THESE]
    assert mock_ui.select_from_list.call_count == 1


def test_prompt_clarification_rejects_sentinel_combined_with_a_real_option():
    mock_ui = MagicMock()
    mock_ui.select_from_list.side_effect = [
        ["A", _NOT_SURE],  # invalid: mixed with a real option
        ["A"],  # corrected on retry
    ]
    generator = TaxonomyConceptFilterGenerator(ui=mock_ui)

    result = generator._prompt_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B"])
    )

    assert result == ["A"]
    assert mock_ui.select_from_list.call_count == 2


def test_prompt_clarification_rejects_both_sentinels_combined():
    """Not sure and none of these are contradictory signals — pick one."""
    mock_ui = MagicMock()
    mock_ui.select_from_list.side_effect = [
        [_NOT_SURE, _NONE_OF_THESE],  # invalid: mutually exclusive
        [_NOT_SURE],  # corrected on retry
    ]
    generator = TaxonomyConceptFilterGenerator(ui=mock_ui)

    result = generator._prompt_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B"])
    )

    assert result == [_NOT_SURE]
    assert mock_ui.select_from_list.call_count == 2


def test_prompt_clarification_defaults_to_the_not_sure_option():
    """Pressing Enter with no thought must not silently pick the LLM's first option,
    and must default to uncertainty, not a confident "none of these apply"."""
    mock_ui = MagicMock()
    generator = TaxonomyConceptFilterGenerator(ui=mock_ui)

    generator._prompt_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B", "C"])
    )

    _, kwargs = mock_ui.select_from_list.call_args
    assert kwargs["default"] == [5]  # 1-indexed; "I'm not sure" is the 5th of 5 options


# ---------------------------------------------------------------------------
# forward — driving ResumableReAct step by step
# ---------------------------------------------------------------------------


def test_forward_drives_the_agent_step_by_step_to_completion():
    step0 = _step(0, "mark_unsatisfiable", {"reason": "no match"})
    generator = _generator_with_mock_agent(start_returns=step0)

    result = _forward(generator)

    generator.agent.resume.assert_called_once_with(
        step0, user_query=UserQuery(query="q")
    )
    assert result.reasoning == "done"


def test_forward_captures_the_unsatisfiable_reason_from_the_step_args():
    """No stateful tool needed — the reason is read straight off tool_args,
    which the caller already sees before the (now-real, stateless) tool
    runs."""
    step0 = _step(0, "mark_unsatisfiable", {"reason": "no matching concept"})
    generator = _generator_with_mock_agent(start_returns=step0)

    result = _forward(generator)

    assert result.unsatisfiable_reason == "no matching concept"


def test_forward_reason_does_not_leak_between_calls():
    unsatisfiable_step = _step(0, "mark_unsatisfiable", {"reason": "no match"})
    generator = _generator_with_mock_agent(start_returns=unsatisfiable_step)
    first = _forward(generator, "q1")
    assert first.unsatisfiable_reason == "no match"

    generator._build_agent.return_value.start = MagicMock(return_value=_final())
    second = _forward(generator, "q2")
    assert second.unsatisfiable_reason is None


def test_forward_answers_a_clarification_step_via_the_ui_and_resumes():
    mock_ui = MagicMock()
    mock_ui.select_from_list.return_value = ["intervention"]
    clarification_step = _step(
        0,
        "ask_for_clarification",
        _request("Which scheme?", ["intervention", "outcome"]),
    )
    generator = _generator_with_mock_agent(ui=mock_ui, start_returns=clarification_step)

    _forward(generator)

    resumed_with = generator.agent.resume.call_args.args[0]
    assert resumed_with.trajectory["observation_0"] == ["intervention"]


def test_forward_prints_the_reasoning_behind_a_clarification_step_too():
    """The agent's thought for *why* it's asking should be visible before the
    question itself — not just skipped because the tool happens to be
    ask_for_clarification."""
    mock_ui = MagicMock()
    mock_ui.select_from_list.return_value = ["intervention"]
    clarification_step = _step(
        0,
        "ask_for_clarification",
        _request("Which scheme?", ["intervention", "outcome"]),
    )
    generator = _generator_with_mock_agent(ui=mock_ui, start_returns=clarification_step)

    _forward(generator)

    mock_ui.print_reasoning.assert_called_once_with("Step 0", "thinking")


def test_forward_prints_every_step_live_when_a_ui_is_given():
    mock_ui = MagicMock()
    search_step = _step(0, "some_other_tool")
    generator = _generator_with_mock_agent(ui=mock_ui, start_returns=search_step)

    _forward(generator)

    mock_ui.print_reasoning.assert_called_once_with("Step 0", "thinking")


def test_forward_does_not_touch_ui_when_none_is_given():
    step0 = _step(0, "some_other_tool")
    generator = _generator_with_mock_agent(start_returns=step0)

    # Would raise if forward() ever touched self.ui — there isn't one.
    _forward(generator)


def test_ask_for_clarification_only_registered_as_a_tool_when_ui_given():
    empty_vocab = IndexedVocab(concepts=[], local_ref_to_iri={})

    without_ui = TaxonomyConceptFilterGenerator()
    agent_without_ui = without_ui._build_agent(empty_vocab, MagicMock())
    assert "ask_for_clarification" not in agent_without_ui.tools

    with_ui = TaxonomyConceptFilterGenerator(ui=MagicMock())
    agent_with_ui = with_ui._build_agent(empty_vocab, MagicMock())
    assert "ask_for_clarification" in agent_with_ui.tools
