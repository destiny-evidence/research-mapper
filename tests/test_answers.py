import pytest

from research_mapper.engine.answers import InvalidAnswer, validate_answer
from research_mapper.engine.enums import DecisionType
from research_mapper.engine.models import Decision

ONE = {"query": "a"}
TWO = {"query": "b"}


def decision(**constraints) -> Decision:
    return Decision(
        type=DecisionType.SELECT_MANY,
        key="pick",
        prompt="pick some",
        options=[
            {"id": "1", "label": "a", "value": ONE},
            {"id": "2", "label": "b", "value": TWO},
        ],
        constraints=constraints,
    )


def test_accepts_a_subset_of_what_was_offered():
    validate_answer(decision(), [ONE])
    validate_answer(decision(), [ONE, TWO])
    validate_answer(decision(), [])


@pytest.mark.parametrize("answer", [["a"], [1], "a", [None]])
def test_rejects_anything_that_is_not_a_list_of_records(answer):
    with pytest.raises(InvalidAnswer):
        validate_answer(decision(), answer)


def test_rejects_records_that_were_never_offered():
    """Otherwise a bad answer becomes a red operation the worker discovers."""
    with pytest.raises(InvalidAnswer):
        validate_answer(decision(), [{"query": "invented"}])


def test_allow_new_permits_invented_records():
    validate_answer(decision(allow_new=True), [{"query": "invented"}])


def test_enforces_min_and_max():
    with pytest.raises(InvalidAnswer):
        validate_answer(decision(min=1), [])
    with pytest.raises(InvalidAnswer):
        validate_answer(decision(max=1), [ONE, TWO])
    validate_answer(decision(min=1, max=2), [ONE])
