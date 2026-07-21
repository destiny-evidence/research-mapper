import pytest

from research_mapper.models.mapping import DimensionSubTopic, MappingDimension
from research_mapper.models.sparse_search import LuceneQuery
from research_mapper.ui.tui import TerminalUI


def _queries(*strings):
    return [LuceneQuery(query=s) for s in strings]


@pytest.fixture
def dimensions():
    return (
        MappingDimension(
            name="Cost-effectiveness",
            description="Economic costs and benefits of interventions.",
        ),
        MappingDimension(
            name="Patient outcomes",
            description="Health outcomes experienced by patients.",
        ),
        MappingDimension(
            name="Implementation barriers",
            description="Barriers to real-world adoption.",
        ),
    )


@pytest.fixture
def subtopics():
    return [
        DimensionSubTopic(
            name="Direct costs", description="Costs borne directly by providers."
        ),
        DimensionSubTopic(
            name="Indirect costs", description="Downstream/societal costs."
        ),
        DimensionSubTopic(
            name="Cost-utility analyses", description="QALY-based comparisons."
        ),
    ]


class FakeUI(TerminalUI):
    """A TerminalUI whose `input` replays a scripted sequence of responses."""

    def __init__(self, responses):
        super().__init__()
        self._responses = iter(responses)

    def input(self, *args, spacing: bool = True, **kwargs) -> str:
        return next(self._responses)


# ---------------------------------------------------------------------------
# select_from_list — filtering suggested items via index selection
# (e.g. screening criteria, search results)
# ---------------------------------------------------------------------------


def test_select_from_list_empty_input_keeps_all():
    queries = _queries("climate AND health", "heat AND mortality", "flood AND disease")
    ui = FakeUI(responses=[""])
    result = ui.select_from_list(queries, title="Suggested queries")
    assert result == queries


def test_select_from_list_subset():
    queries = _queries("climate AND health", "heat AND mortality", "flood AND disease")
    ui = FakeUI(responses=["1 3"])
    result = ui.select_from_list(queries, title="Suggested queries")
    assert len(result) == 2
    assert result[0].query == "climate AND health"
    assert result[1].query == "flood AND disease"


def test_select_from_list_reprompts_on_invalid_input():
    queries = _queries("climate AND health", "heat AND mortality")
    ui = FakeUI(responses=["1 abc", "5", "1"])
    result = ui.select_from_list(queries, title="Suggested queries")
    assert len(result) == 1
    assert result[0].query == "climate AND health"


# ---------------------------------------------------------------------------
# confirm_or_replace — reviewing top-level mapping dimensions
# (accept all outright, or replace individually by name — dimensions are a
# fixed-size collection and cannot be dropped)
# ---------------------------------------------------------------------------


def test_confirm_or_replace_accepts_dimensions_outright(dimensions):
    ui = FakeUI(responses=["y"])
    result = ui.confirm_or_replace(
        dimensions, title="Suggested dimensions", noun="dimensions"
    )
    assert tuple(result) == dimensions


def test_confirm_or_replace_reprompts_on_invalid_accept_response(dimensions):
    ui = FakeUI(responses=["maybe", "y"])
    result = ui.confirm_or_replace(dimensions, noun="dimensions")
    assert tuple(result) == dimensions


def test_confirm_or_replace_rejected_keeps_unedited_dimensions(dimensions):
    ui = FakeUI(responses=["n", "", "", ""])
    result = ui.confirm_or_replace(dimensions, noun="dimensions")
    assert tuple(result) == dimensions


def test_confirm_or_replace_replaces_named_dimension_with_blank_description(dimensions):
    ui = FakeUI(responses=["n", "", "Equity", ""])
    result = ui.confirm_or_replace(dimensions, noun="dimensions")
    assert len(result) == 3
    assert result[0] == dimensions[0]
    assert result[1] == MappingDimension(name="Equity", description="")
    assert result[2] == dimensions[2]


def test_confirm_or_replace_without_allow_drop_treats_dash_as_a_literal_name(
    dimensions,
):
    ui = FakeUI(responses=["n", "-", "", ""])
    result = ui.confirm_or_replace(dimensions, noun="dimensions", allow_drop=False)
    assert len(result) == 3
    assert result[0] == MappingDimension(name="-", description="")


# ---------------------------------------------------------------------------
# confirm_or_replace — reviewing dimension subtopics
# (accept all outright, replace by name, or drop individually — subtopics may
# be removed entirely)
# ---------------------------------------------------------------------------


def test_confirm_or_replace_accepts_subtopics_outright(subtopics):
    ui = FakeUI(responses=["y"])
    result = ui.confirm_or_replace(
        subtopics, title="Subtopics", noun="subtopics", allow_drop=True
    )
    assert result == subtopics


def test_confirm_or_replace_can_drop_a_subtopic(subtopics):
    ui = FakeUI(responses=["n", "-", "", ""])
    result = ui.confirm_or_replace(subtopics, noun="subtopics", allow_drop=True)
    assert len(result) == 2
    assert subtopics[0] not in result
    assert result == subtopics[1:]


def test_confirm_or_replace_can_drop_all_subtopics(subtopics):
    ui = FakeUI(responses=["n", "-", "-", "-"])
    result = ui.confirm_or_replace(subtopics, noun="subtopics", allow_drop=True)
    assert result == []


def test_confirm_or_replace_can_replace_and_drop_in_combination(subtopics):
    ui = FakeUI(responses=["n", "Out-of-pocket costs", "", "-"])
    result = ui.confirm_or_replace(subtopics, noun="subtopics", allow_drop=True)
    assert len(result) == 2
    assert result[0] == DimensionSubTopic(name="Out-of-pocket costs", description="")
    assert result[1] == subtopics[1]
