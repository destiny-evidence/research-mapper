from typing import Literal

import dspy

from research_mapper.models import (
    MappingDimensionWithSubTopics,
    Evidence,
    UserQuery,
)


def mapping_along_dimensions_signature_builder(
    mapping_dimension1: MappingDimensionWithSubTopics,
    mapping_dimension2: MappingDimensionWithSubTopics,
    mapping_dimension3: MappingDimensionWithSubTopics,
) -> type[dspy.Signature]:
    """
    Dynamically builds a dspy.Signature for mapping a piece of evidence to a subtopic of each of
    the 3 provided dimensions, constraining each output field to that dimension's subtopic names
    via a dynamically-built typing.Literal.
    :param mapping_dimension1: the first mapping dimension, with its finalised subtopics
    :param mapping_dimension2: the second mapping dimension, with its finalised subtopics
    :param mapping_dimension3: the third mapping dimension, with its finalised subtopics
    :return: a dynamically-built MapEvidenceAlongDimensions signature
    :raises ValueError: if any of the provided dimensions has no subtopics
    """
    for dimension in (mapping_dimension1, mapping_dimension2, mapping_dimension3):
        if not dimension.subtopics:
            raise ValueError(
                f"Dimension '{dimension.name}' has no subtopics to map evidence against."
            )

    Dim1SubTopicsLiteral = Literal[
        tuple(sub.name for sub in mapping_dimension1.subtopics)
    ]
    Dim2SubTopicsLiteral = Literal[
        tuple(sub.name for sub in mapping_dimension2.subtopics)
    ]
    Dim3SubTopicsLiteral = Literal[
        tuple(sub.name for sub in mapping_dimension3.subtopics)
    ]
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
        "dimension1_subtopic": Dim1SubTopicsLiteral,
        "dimension2_subtopic": Dim2SubTopicsLiteral,
        "dimension3_subtopic": Dim3SubTopicsLiteral,
    }
    return type(
        "MapEvidenceAlongDimensions",
        (dspy.Signature,),
        {**fields, "__annotations__": annotations, "__doc__": docstring},
    )
