from unittest.mock import MagicMock

import pytest

from research_mapper.models.common import UserQuery
from research_mapper.models.react import Step
from research_mapper.models.taxonomy_search import (
    ClarificationOptions,
    Concept,
    ConceptFilterGroup,
    IndexedVocab,
)
from research_mapper.modules.taxonomy_search import (
    TaxonomyConceptFilterGenerator,
    UnknownConceptRefError,
)

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
    """A generator whose build_agent is stubbed to return a mock agent — the
    real agent now depends on per-call indexed/graph (bound taxonomy-browsing
    tools), so it can no longer just be swapped in after construction."""
    generator = TaxonomyConceptFilterGenerator(ui=ui)
    mock_agent = MagicMock()
    mock_agent.start = MagicMock(return_value=start_returns)
    mock_agent.resume = MagicMock(return_value=resume_returns or _final())
    generator.build_agent = MagicMock(return_value=mock_agent)
    return generator


def _forward(generator: TaxonomyConceptFilterGenerator, query: str = "q", indexed=None):
    return generator.forward(
        UserQuery(query=query), indexed=indexed or MagicMock(), graph=MagicMock()
    )


def _indexed_vocab() -> IndexedVocab:
    return IndexedVocab(
        concepts=[
            Concept(local_ref="C10", scheme="Setting", label="Primary Education"),
            Concept(local_ref="C11", scheme="Setting", label="Secondary Education"),
        ],
        local_ref_to_iri={
            "C10": "https://example.org/C10",
            "C11": "https://example.org/C11",
        },
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


def test_prompt_clarification_allows_not_sure_combined_with_a_real_option():
    """ "I'm not sure" is a hedge, not a contradiction — "I think it's probably
    A, but I'm not sure" is a coherent answer, unlike combining with "None of
    these", which is a real contradiction."""
    mock_ui = MagicMock()
    mock_ui.select_from_list.return_value = ["A", _NOT_SURE]
    generator = TaxonomyConceptFilterGenerator(ui=mock_ui)

    result = generator._prompt_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B"])
    )

    assert result == ["A", _NOT_SURE]
    assert mock_ui.select_from_list.call_count == 1


def test_prompt_clarification_rejects_none_of_these_combined_with_a_real_option():
    mock_ui = MagicMock()
    mock_ui.select_from_list.side_effect = [
        ["A", _NONE_OF_THESE],  # invalid: a real contradiction
        ["A"],  # corrected on retry
    ]
    generator = TaxonomyConceptFilterGenerator(ui=mock_ui)

    result = generator._prompt_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B"])
    )

    assert result == ["A"]
    assert mock_ui.select_from_list.call_count == 2


def test_prompt_clarification_rejects_both_sentinels_combined():
    """None of these still can't combine with anything, including not sure."""
    mock_ui = MagicMock()
    mock_ui.select_from_list.side_effect = [
        [_NOT_SURE, _NONE_OF_THESE],  # invalid: none of these can't combine
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
        step0, user_query=UserQuery(query="q"), available_concepts=""
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


def test_forward_captures_the_reason_from_a_raise_attempted_prompt_attack_step():
    """raise_attempted_prompt_attack is captured the same way as
    mark_unsatisfiable — both are real, trivial functions the caller reads
    tool_args from directly, rather than stubs the loop must intercept."""
    step0 = _step(
        0, "raise_attempted_prompt_attack", {"reason": "unrelated to the taxonomy"}
    )
    generator = _generator_with_mock_agent(start_returns=step0)

    result = _forward(generator)

    assert result.unsatisfiable_reason == "unrelated to the taxonomy"


def test_forward_reason_does_not_leak_between_calls():
    unsatisfiable_step = _step(0, "mark_unsatisfiable", {"reason": "no match"})
    generator = _generator_with_mock_agent(start_returns=unsatisfiable_step)
    first = _forward(generator, "q1")
    assert first.unsatisfiable_reason == "no match"

    generator.build_agent.return_value.start = MagicMock(return_value=_final())
    second = _forward(generator, "q2")
    assert second.unsatisfiable_reason is None


def test_forward_passes_the_concept_listing_to_start_and_resume():
    indexed = _indexed_vocab()
    step0 = _step(0, "some_other_tool")
    generator = _generator_with_mock_agent(start_returns=step0)

    _forward(generator, indexed=indexed)

    expected_listing = (
        "C10\tSetting: Primary Education\nC11\tSetting: Secondary Education"
    )
    generator.agent.start.assert_called_once_with(
        user_query=UserQuery(query="q"), available_concepts=expected_listing
    )
    generator.agent.resume.assert_called_once_with(
        step0, user_query=UserQuery(query="q"), available_concepts=expected_listing
    )


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


# ---------------------------------------------------------------------------
# concept_listing — the upfront "scheme: label" index
# ---------------------------------------------------------------------------


def test_concept_listing_formats_every_concept_as_scheme_label_sorted():
    """Labels repeat across schemes (confirmed on real HPV/ESEA data), so each
    line is scheme-qualified; sorted so the same taxonomy always renders the
    same listing, regardless of concept insertion order."""
    generator = TaxonomyConceptFilterGenerator()
    indexed = IndexedVocab(
        concepts=[
            Concept(local_ref="C2", scheme="Setting", label="Secondary Education"),
            Concept(local_ref="C1", scheme="Country", label="Kenya"),
            Concept(local_ref="C3", scheme="Setting", label="Primary Education"),
        ],
        local_ref_to_iri={},
    )

    result = generator.concept_listing(indexed)

    assert result == (
        "C1\tCountry: Kenya\n"
        "C3\tSetting: Primary Education\n"
        "C2\tSetting: Secondary Education"
    )


def test_concept_listing_shows_the_refs_the_agent_must_cite():
    """The agent answers in local_refs; if the listing omits them it can only
    echo back a label, which validation then rejects."""
    generator = TaxonomyConceptFilterGenerator()
    indexed = _indexed_vocab()

    listing = generator.concept_listing(indexed)

    for concept in indexed.concepts:
        assert concept.local_ref in listing


def test_concept_listing_empty_for_no_concepts():
    generator = TaxonomyConceptFilterGenerator()
    assert (
        generator.concept_listing(IndexedVocab(concepts=[], local_ref_to_iri={})) == ""
    )


# ---------------------------------------------------------------------------
# forward — validating the agent's final concept_local_refs
# ---------------------------------------------------------------------------


def test_forward_raises_for_an_unknown_concept_local_ref():
    """This is the real crash the user hit: the agent mis-parsed a local_ref
    out of a compound display string and cited one that was never a real
    concept, which used to surface as a bare KeyError deep in a TUI lambda
    instead of a clear error at the point the bad ref was produced."""
    final = _final()
    final.filter_groups = [
        ConceptFilterGroup(
            scheme="Setting",
            concept_local_refs=["C10: Primary Education"],
            reason="matches",
        )
    ]
    generator = _generator_with_mock_agent(start_returns=final)

    with pytest.raises(UnknownConceptRefError, match="C10: Primary Education"):
        _forward(generator, indexed=_indexed_vocab())


def test_forward_suggests_close_matching_labels_for_an_unknown_ref():
    final = _final()
    final.filter_groups = [
        ConceptFilterGroup(
            scheme="Setting",
            concept_local_refs=["C10: Primary Education"],
            reason="matches",
        )
    ]
    generator = _generator_with_mock_agent(start_returns=final)

    with pytest.raises(UnknownConceptRefError, match="Did you mean.*Primary Education"):
        _forward(generator, indexed=_indexed_vocab())


def test_forward_accepts_known_concept_local_refs():
    final = _final()
    final.filter_groups = [
        ConceptFilterGroup(
            scheme="Setting", concept_local_refs=["C10"], reason="matches"
        )
    ]
    generator = _generator_with_mock_agent(start_returns=final)

    result = _forward(generator, indexed=_indexed_vocab())

    assert result.filter_groups == final.filter_groups


def test_ask_for_clarification_only_registered_as_a_tool_when_ui_given():
    empty_vocab = IndexedVocab(concepts=[], local_ref_to_iri={})

    without_ui = TaxonomyConceptFilterGenerator()
    agent_without_ui = without_ui.build_agent(empty_vocab, MagicMock())
    assert "ask_for_clarification" not in agent_without_ui.tools

    with_ui = TaxonomyConceptFilterGenerator(ui=MagicMock())
    agent_with_ui = with_ui.build_agent(empty_vocab, MagicMock())
    assert "ask_for_clarification" in agent_with_ui.tools


def test_mark_unsatisfiable_and_prompt_attack_are_always_registered():
    """Unlike ask_for_clarification, neither needs a UI to answer through —
    both are real, trivial functions read straight off tool_args."""
    empty_vocab = IndexedVocab(concepts=[], local_ref_to_iri={})
    generator = TaxonomyConceptFilterGenerator()

    agent = generator.build_agent(empty_vocab, MagicMock())

    assert "mark_unsatisfiable" in agent.tools
    assert "raise_attempted_prompt_attack" in agent.tools


def test_an_unknown_ref_is_suggested_as_a_ref_not_a_label():
    generator = TaxonomyConceptFilterGenerator()
    indexed = IndexedVocab(
        concepts=[Concept(local_ref="C7", scheme="Misinformation", label="Addressing")],
        local_ref_to_iri={"C7": "https://example.org/C7"},
    )
    groups = [
        ConceptFilterGroup(
            scheme="Misinformation", concept_local_refs=["Addressing"], reason="r"
        )
    ]

    with pytest.raises(UnknownConceptRefError) as caught:
        generator.validate_filter_groups(groups, indexed)

    assert "C7 (Misinformation: Addressing)" in str(caught.value)


def test_unknown_ref_suggestions_prefer_the_cited_scheme():
    """Labels repeat across schemes (confirmed on real HPV/ESEA data — e.g.
    "Caregivers" in 3 different schemes), so a naive vocabulary-wide fuzzy
    match could point at the wrong concept entirely. Scoping to the group's
    own scheme first resolves the ambiguity correctly."""
    generator = TaxonomyConceptFilterGenerator()
    indexed = IndexedVocab(
        concepts=[
            Concept(local_ref="C1", scheme="Setting", label="Caregivers"),
            Concept(local_ref="C2", scheme="Target Group", label="Caregivers"),
        ],
        local_ref_to_iri={},
    )
    groups = [
        ConceptFilterGroup(
            scheme="Target Group", concept_local_refs=["Caregivers"], reason="r"
        )
    ]

    with pytest.raises(UnknownConceptRefError) as caught:
        generator.validate_filter_groups(groups, indexed)

    message = str(caught.value)
    assert "C2 (Target Group: Caregivers)" in message
    assert "C1 (Setting: Caregivers)" not in message


def test_unknown_ref_suggestions_fall_back_to_the_whole_vocabulary():
    """If the cited scheme itself has nothing close (e.g. it too was
    mis-cited), suggestions should still surface a real concept from
    elsewhere rather than coming up empty."""
    generator = TaxonomyConceptFilterGenerator()
    indexed = IndexedVocab(
        concepts=[
            Concept(local_ref="C1", scheme="Setting", label="Primary Education"),
            Concept(local_ref="C2", scheme="Other Scheme", label="Unrelated"),
        ],
        local_ref_to_iri={},
    )
    groups = [
        ConceptFilterGroup(
            scheme="Other Scheme",
            concept_local_refs=["Primary Education"],
            reason="r",
        )
    ]

    with pytest.raises(UnknownConceptRefError) as caught:
        generator.validate_filter_groups(groups, indexed)

    assert "C1 (Setting: Primary Education)" in str(caught.value)
