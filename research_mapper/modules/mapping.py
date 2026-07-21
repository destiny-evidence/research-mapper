import dspy

from research_mapper.models.common import Evidence, UserQuery
from research_mapper.models.mapping import (
    MappingDimension,
    MappingDimensionWithSubTopics,
)
from research_mapper.signatures.mapping import (
    EvidenceMappingDimensionsFromQuery,
    SubtopicFromEvidenceMappingDimension,
    mapping_along_dimensions_signature_builder,
)


class DimensionGenerator(dspy.Module):
    """
    Generates 3 suggested dimensions to map evidence across for a user's query.
    """

    def __init__(self) -> None:
        self.generate = dspy.ChainOfThought(EvidenceMappingDimensionsFromQuery)

    def forward(self, user_query: UserQuery) -> dspy.Prediction:
        """
        Generates 3 candidate mapping dimensions for a user's query.
        :param user_query: the user's query to generate mapping dimensions for
        :return: a Prediction wrapping dimension1, dimension2, dimension3, and reasoning
        """
        return self.generate(original_query=user_query)


class SubtopicGenerator(dspy.Module):
    """
    Generates suggested subtopics for a single mapping dimension. Intended to be driven over many
    dimensions via `dspy.Module.batch`.
    """

    def __init__(self) -> None:
        self.generate = dspy.ChainOfThought(SubtopicFromEvidenceMappingDimension)

    def forward(
        self,
        user_query: UserQuery,
        dimension: MappingDimension,
        other_dimensions: list[MappingDimension],
    ) -> dspy.Prediction:
        """
        Generates subtopics for a mapping dimension.
        :param user_query: the user's original query, for context
        :param dimension: the mapping dimension to generate subtopics for
        :param other_dimensions: the other top-level mapping dimensions, for context
        :return: a Prediction wrapping the suggested subtopics and reasoning
        """
        return self.generate(
            original_query=user_query,
            dimension=dimension,
            other_dimensions=other_dimensions,
        )


class EvidenceMapper(dspy.Module):
    """
    Maps a single piece of evidence to a coordinate across a set of finalised mapping dimensions
    (each with their finalised subtopics). Intended to be driven over many pieces of evidence via
    `dspy.Module.batch`.
    """

    def forward(
        self,
        user_query: UserQuery,
        evidence: Evidence,
        dimensions: tuple[
            MappingDimensionWithSubTopics,
            MappingDimensionWithSubTopics,
            MappingDimensionWithSubTopics,
        ],
    ) -> dspy.Prediction:
        """
        Maps a piece of evidence to a coordinate across the given dimensions and their subtopics.
        :param user_query: the user's original query, for context
        :param evidence: the piece of evidence to map
        :param dimensions: the finalised mapping dimensions, each with their finalised subtopics
        :return: a Prediction wrapping the evidence's coordinate (as dimension1_subtopic,
            dimension2_subtopic, dimension3_subtopic) and reasoning
        :raises RuntimeError: if a mapping dimension somehow has no subtopics to map evidence against
        """
        try:
            MapEvidenceAlongDimensions = mapping_along_dimensions_signature_builder(
                *dimensions
            )
        except ValueError as exc:
            raise RuntimeError(
                f"A mapping dimension happened to have no subtopics somehow: {exc}. Please restart and try again."
            ) from exc
        map_evidence_along_dimensions = dspy.ChainOfThought(MapEvidenceAlongDimensions)
        return map_evidence_along_dimensions(
            original_query=user_query, evidence=evidence, dimensions=dimensions
        )
