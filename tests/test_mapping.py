import uuid
from unittest.mock import MagicMock

import pytest

from research_mapper.models import (
    DimensionSubTopic,
    Evidence,
    MappingDimension,
    MappingDimensionWithSubTopics,
    UserQuery,
)
from research_mapper.modules.mapping import (
    DimensionGenerator,
    EvidenceMapper,
    SubtopicGenerator,
)


@pytest.fixture(scope="module", autouse=True)
def _live(live_setup):
    pass


def test_dimension_generator_returns_generator_prediction():
    """DimensionGenerator.forward is a pure passthrough to its ChainOfThought."""
    mock_prediction = MagicMock()
    generator = DimensionGenerator()
    generator.generate = MagicMock(return_value=mock_prediction)

    result = generator.forward(UserQuery(query="test"))

    generator.generate.assert_called_once()
    assert result is mock_prediction


def test_subtopic_generator_returns_generator_prediction():
    """SubtopicGenerator.forward is a pure passthrough to its ChainOfThought."""
    mock_prediction = MagicMock()
    generator = SubtopicGenerator()
    generator.generate = MagicMock(return_value=mock_prediction)

    dimension = MappingDimension(
        name="Geography", description="Where the study took place"
    )
    other_dimensions = [
        MappingDimension(name="Time", description="When the study took place")
    ]

    result = generator.forward(UserQuery(query="test"), dimension, other_dimensions)

    generator.generate.assert_called_once()
    assert result is mock_prediction


@pytest.mark.integration
def test_evidence_mapper_end_to_end():
    mapper = EvidenceMapper()
    query = UserQuery(
        query="what are the best interventions to mitigate the health risks of climate change"
    )
    evidence = Evidence(
        destiny_id=uuid.uuid4(),
        title="Heat stress and cardiovascular mortality: a systematic review",
        abstract="This review examines interventions that reduce cardiovascular death due to heat exposure in urban populations, including cooling centres and early warning systems.",
        authors=["Smith J", "Jones K"],
        year=2022,
    )
    dimensions = (
        MappingDimensionWithSubTopics(
            name="Geography",
            description="Where the study took place",
            subtopics=[
                DimensionSubTopic(name="Urban", description="Urban settings"),
                DimensionSubTopic(name="Rural", description="Rural settings"),
            ],
        ),
        MappingDimensionWithSubTopics(
            name="Intervention type",
            description="The type of intervention studied",
            subtopics=[
                DimensionSubTopic(
                    name="Infrastructure", description="Physical infrastructure changes"
                ),
                DimensionSubTopic(
                    name="Policy", description="Policy or regulatory interventions"
                ),
            ],
        ),
        MappingDimensionWithSubTopics(
            name="Health outcome",
            description="The health outcome studied",
            subtopics=[
                DimensionSubTopic(
                    name="Cardiovascular", description="Cardiovascular outcomes"
                ),
                DimensionSubTopic(
                    name="Respiratory", description="Respiratory outcomes"
                ),
            ],
        ),
    )

    result = mapper(user_query=query, evidence=evidence, dimensions=dimensions)

    assert result.dimension1_subtopic in {s.name for s in dimensions[0].subtopics}
    assert result.dimension2_subtopic in {s.name for s in dimensions[1].subtopics}
    assert result.dimension3_subtopic in {s.name for s in dimensions[2].subtopics}
