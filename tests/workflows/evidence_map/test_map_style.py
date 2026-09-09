"""Choosing which of the two maps to build."""

import pytest

from factories import make_operation, make_session, make_user
from research_mapper.engine.context import NeedsInput, StepContext
from research_mapper.engine.enums import DecisionType
from research_mapper.engine.models import Decision
from research_mapper.workflows.evidence_map.steps.map_style import ChooseMapStyle


@pytest.fixture
def operation(db):
    user = make_user(db)
    session = make_session(db, user)
    return make_operation(db, session, user, type="choose_map_style")


def test_asks_which_map_to_build(operation, session_factory):
    ctx = StepContext(operation.id, session_factory)
    with pytest.raises(NeedsInput):
        ChooseMapStyle().run(ctx, ChooseMapStyle.Params())

    spec = ctx.pending_decisions["map_style"]
    assert spec.type == "select_one"
    assert [option["id"] for option in spec.options] == ["suggested", "taxonomy"]
    # The UI shows these under each option; a bare pair of labels would not say
    # what the difference is.
    assert all(option["detail"] for option in spec.options)


def test_reports_the_style_that_was_chosen(db, operation, session_factory):
    db.add(
        Decision(
            research_session_id=operation.research_session_id,
            operation_id=operation.id,
            type=DecisionType.SELECT_ONE,
            key="map_style",
            prompt="How should the map be built?",
            answer=[{"style": "taxonomy"}],
        )
    )
    db.commit()

    result = ChooseMapStyle().run(
        StepContext(operation.id, session_factory), ChooseMapStyle.Params()
    )
    assert result == {"style": "taxonomy"}


def test_settles_a_question_without_checkpointing_the_session():
    """A fork cuts at the decision, so this step has no state to be a version of."""
    assert ChooseMapStyle.mutates_state is False
