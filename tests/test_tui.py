import uuid

import pytest

from research_mapper.models.common import Evidence
from research_mapper.models.mapping import (
    DimensionSubTopic,
    EvidenceMap,
    MappedEvidence,
    MappingDimension,
    MappingDimensionWithSubTopics,
)
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


def test_select_from_list_empty_input_uses_default_when_given():
    queries = _queries("climate AND health", "heat AND mortality", "flood AND disease")
    ui = FakeUI(responses=[""])
    result = ui.select_from_list(queries, title="Pick one", default=[2])
    assert len(result) == 1
    assert result[0].query == "heat AND mortality"


# ---------------------------------------------------------------------------
# print_table — display-only, no selection prompt
# ---------------------------------------------------------------------------


def test_print_table_does_not_prompt_for_input():
    """Unlike select_from_list/select_one, print_table never reads from input."""
    queries = _queries("climate AND health", "heat AND mortality")
    ui = FakeUI(responses=[])  # would raise StopIteration if input() were called
    ui.print_table(queries, title="Applied queries")


# ---------------------------------------------------------------------------
# select_one — picking exactly one item from a small fixed list
# (e.g. search mode, community)
# ---------------------------------------------------------------------------


def test_select_one_empty_input_returns_default():
    queries = _queries("climate AND health", "heat AND mortality")
    ui = FakeUI(responses=[""])
    result = ui.select_one(queries, title="Pick one", default=2)
    assert result.query == "heat AND mortality"


def test_select_one_returns_chosen_item():
    queries = _queries("climate AND health", "heat AND mortality", "flood AND disease")
    ui = FakeUI(responses=["3"])
    result = ui.select_one(queries, title="Pick one")
    assert result.query == "flood AND disease"


def test_select_one_reprompts_on_invalid_input():
    queries = _queries("climate AND health", "heat AND mortality")
    ui = FakeUI(responses=["abc", "5", "2"])
    result = ui.select_one(queries, title="Pick one")
    assert result.query == "heat AND mortality"


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


# ---------------------------------------------------------------------------
# print_evidence_map — an evidence item with multiple subtopics within one
# dimension (e.g. multiple taxonomy concepts in one scheme) must appear in every
# grid cell/cluster it belongs to, not just the first.
# ---------------------------------------------------------------------------


def _mapping_dimension(
    name: str, *subtopic_names: str
) -> MappingDimensionWithSubTopics:
    return MappingDimensionWithSubTopics(
        name=name,
        description="",
        subtopics=[DimensionSubTopic(name=n, description="") for n in subtopic_names],
    )


def test_print_evidence_map_fans_out_multi_value_coordinate():
    dimensions = (
        _mapping_dimension("Theme", "Access", "Equity"),
        _mapping_dimension("Design", "RCT", "Cohort"),
        _mapping_dimension("Region", "East Africa"),
    )
    evidence_map = EvidenceMap(
        mapped_evidence=[
            MappedEvidence(
                evidence=Evidence(destiny_id=uuid.uuid4(), title="Multi-tagged paper"),
                coordinate={
                    "Theme": ["Access", "Equity"],
                    "Design": ["RCT"],
                    "Region": ["East Africa"],
                },
            )
        ],
        dimensions=dimensions,
    )

    ui = TerminalUI()
    with ui.console.capture() as capture:
        ui.print_evidence_map(evidence_map)
    output = capture.get()

    # row_dim/col_dim are picked by fewest subtopics: Region (1) then Theme (2), so
    # Design becomes the cluster dimension. The item's two Theme values ("Access",
    # "Equity") must both place it in the grid — i.e. its index appears twice.
    assert output.count("1") >= 2
