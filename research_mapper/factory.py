from typing import Literal

import dspy

from research_mapper.models import (
    MappingDimensionWithSubTopics,
    Evidence,
)


def mapping_along_dimensions_signature_builder(
    mapping_dimension1: MappingDimensionWithSubTopics,
    mapping_dimension2: MappingDimensionWithSubTopics,
    mapping_dimension3: MappingDimensionWithSubTopics,
) -> dspy.Signature:
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
        "evidence": dspy.InputField(
            desc="The piece of evidence to map across the dimensions."
        ),
        "dimensions": dspy.InputField(
            desc="The dimensions and their subtopics the piece of evidence is to be mapped across."
        ),
        "mapping_coordinate": dspy.OutputField(
            desc="The coordinate of the piece of evidence in the map."
        ),
    }
    annotations = {
        "evidence": Evidence,
        "dimensions": tuple[
            MappingDimensionWithSubTopics,
            MappingDimensionWithSubTopics,
            MappingDimensionWithSubTopics,
        ],
        "mapping_coordinate": tuple[
            Dim1SubTopicsLiteral, Dim2SubTopicsLiteral, Dim3SubTopicsLiteral
        ],
    }
    return type(
        "MapEvidenceAlongDimensions",
        (dspy.Signature,),
        {**fields, "__annotations__": annotations, "__doc__": docstring},
    )
