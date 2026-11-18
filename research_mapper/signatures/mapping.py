import dspy
from dspy.experimental import Choice


from research_mapper.models.common import Evidence, UserQuery
from research_mapper.models.mapping import (
    DimensionSubTopic,
    MappingDimension,
    MappingDimensionWithSubTopics,
)


class EvidenceMappingDimensionsFromQuery(dspy.Signature):
    """
    Suggest 3 dimensions, e.g. 2 dimensions and 1 facet, to map academic evidence across.
    """

    original_query: UserQuery = dspy.InputField(
        desc="The user's original query that initiated the evidence map."
    )
    dimension1: MappingDimension = dspy.OutputField(
        desc="The first dimension to map the evidence data against."
    )
    dimension2: MappingDimension = dspy.OutputField(
        desc="The second dimension to map the evidence data against."
    )
    dimension3: MappingDimension = dspy.OutputField(
        desc="The third dimension to map the evidence data against."
    )


class SubtopicFromEvidenceMappingDimension(dspy.Signature):
    """
    Suggest a collection of sub-topics/dimensions for a given evidence mapping dimension.
    """

    original_query: UserQuery = dspy.InputField(
        desc="The user's original query that initiated the evidence map."
    )
    other_dimensions: list[MappingDimension] = dspy.InputField(
        desc="The other top-level evidence mapping dimensions that will be used, for context."
    )
    dimension: MappingDimension = dspy.InputField(
        desc="The evidence mapping dimension to generate sub-topics/dimensions for."
    )
    subtopics: list[DimensionSubTopic] = dspy.OutputField(
        desc="The collection of sub-topics/dimensions for the given evidence mapping dimension."
    )


# The Decisions API needs at least two options to choose between.
MIN_SUBTOPICS = 2


def _subtopic_choice(dimension: MappingDimensionWithSubTopics) -> type[Choice]:
    """A Choice over a dimension's subtopics, each described for the model."""
    try:
        return Choice[tuple((sub.name, sub.description) for sub in dimension.subtopics)]
    except ValueError as exc:
        raise ValueError(f"Dimension '{dimension.name}': {exc}") from exc


def mapping_along_dimensions_signature_builder(
    mapping_dimension1: MappingDimensionWithSubTopics,
    mapping_dimension2: MappingDimensionWithSubTopics,
    mapping_dimension3: MappingDimensionWithSubTopics,
) -> type[dspy.Signature]:
    """
    Dynamically builds a dspy.Signature for mapping a piece of evidence to a subtopic of each of
    the 3 provided dimensions. Each output field is a Choice over that dimension's subtopics,
    named and described, so a decision model answers all three in one request.
    :param mapping_dimension1: the first mapping dimension, with its finalised subtopics
    :param mapping_dimension2: the second mapping dimension, with its finalised subtopics
    :param mapping_dimension3: the third mapping dimension, with its finalised subtopics
    :return: a dynamically-built MapEvidenceAlongDimensions signature
    :raises ValueError: if a dimension has fewer than two subtopics, the fewest a decision
        model will choose between, or two subtopics share a name
    """
    for dimension in (mapping_dimension1, mapping_dimension2, mapping_dimension3):
        if len(dimension.subtopics) < MIN_SUBTOPICS:
            raise ValueError(
                f"Dimension '{dimension.name}' needs at least {MIN_SUBTOPICS} subtopics "
                f"to map evidence against, but has {len(dimension.subtopics)}."
            )

    Dim1SubTopicsChoice = _subtopic_choice(mapping_dimension1)
    Dim2SubTopicsChoice = _subtopic_choice(mapping_dimension2)
    Dim3SubTopicsChoice = _subtopic_choice(mapping_dimension3)
    docstring = (
        "Map a piece of evidence across the provided dimensions and their subtopics."
    )
    fields = {
        "original_query": dspy.InputField(
            desc="The user's original query that initiated the evidence map."
        ),
        "evidence": dspy.InputField(
            desc="The piece of evidence to map across the dimensions."
        ),
        "dimensions": dspy.InputField(
            desc="The dimensions and their subtopics the piece of evidence is to be mapped across."
        ),
        "dimension1_subtopic": dspy.OutputField(
            desc=f"The subtopic of '{mapping_dimension1.name}' the piece of evidence belongs to."
        ),
        "dimension2_subtopic": dspy.OutputField(
            desc=f"The subtopic of '{mapping_dimension2.name}' the piece of evidence belongs to."
        ),
        "dimension3_subtopic": dspy.OutputField(
            desc=f"The subtopic of '{mapping_dimension3.name}' the piece of evidence belongs to."
        ),
    }
    annotations = {
        "original_query": UserQuery,
        "evidence": Evidence,
        "dimensions": tuple[
            MappingDimensionWithSubTopics,
            MappingDimensionWithSubTopics,
            MappingDimensionWithSubTopics,
        ],
        "dimension1_subtopic": Dim1SubTopicsChoice,
        "dimension2_subtopic": Dim2SubTopicsChoice,
        "dimension3_subtopic": Dim3SubTopicsChoice,
    }
    return type(
        "MapEvidenceAlongDimensions",
        (dspy.Signature,),
        {**fields, "__annotations__": annotations, "__doc__": docstring},
    )
