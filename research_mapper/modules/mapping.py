import dspy

from research_mapper.models.common import Evidence, UserQuery
from research_mapper.config import get_decision_model, is_dedicated_decision_model
from research_mapper.models.mapping import (
    MappingDimension,
    MappingDimensionWithSubTopics,
)
from research_mapper.signatures.mapping import (
    EvidenceMappingDimensionsFromQuery,
    SubtopicFromEvidenceMappingDimension,
    mapping_along_dimensions_signature_builder,
)


SUBTOPIC_FIELDS = (
    "dimension1_subtopic",
    "dimension2_subtopic",
    "dimension3_subtopic",
)


class DimensionGenerator(dspy.Module):
    """
    Generates 3 suggested dimensions to map evidence across for a user's query.
    """

    def __init__(self) -> None:
        self.generate = dspy.ChainOfThought(
            EvidenceMappingDimensionsFromQuery, rationale_field_type=str
        )

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
        self.generate = dspy.ChainOfThought(
            SubtopicFromEvidenceMappingDimension, rationale_field_type=str
        )

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

    def __init__(self, lm: dspy.LM | None = None) -> None:
        # The signature depends on each call's dimensions, so the predictor is built per
        # call and only the LM to give it is kept. None means the configured decision model.
        self._lm = lm

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
        :return: a Prediction of plain values: the evidence's coordinate as subtopic names
            (dimension1_subtopic, dimension2_subtopic, dimension3_subtopic), probabilities
            (each dimension's name to its subtopics' probabilities), model, whether it is a
            dedicated decision model (dedicated), and reasoning
        :raises RuntimeError: if a mapping dimension's subtopics can't be chosen between
        """
        try:
            MapEvidenceAlongDimensions = mapping_along_dimensions_signature_builder(
                *dimensions
            )
        except ValueError as exc:
            raise RuntimeError(
                f"Can't map evidence across these dimensions: {exc}"
            ) from exc
        # A local, not an attribute: batch shares this module across threads.
        mapper = dspy.Predict(MapEvidenceAlongDimensions)
        mapper.set_lm(self._lm or get_decision_model())
        pred = mapper(
            original_query=user_query, evidence=evidence, dimensions=dimensions
        )

        subtopics: dict[str, str] = {}
        probabilities: dict[str, dict[str, float]] = {}
        lines = []
        for dimension, field in zip(dimensions, SUBTOPIC_FIELDS, strict=True):
            choice = pred[field]  # a Choice; it stays inside this module
            subtopics[field] = choice.value
            probabilities[dimension.name] = dict(choice.probabilities or {})
            chosen = probabilities[dimension.name].get(choice.value)
            likelihood = f"{chosen:.0%} ({chosen:.4f}), " if chosen is not None else ""
            lines.append(
                f"{dimension.name}: {choice.value} "
                f"({likelihood}confidence {choice.confidence:.0%})"
            )
        reasoning = "Mapped as " + "; ".join(lines) + f", per {mapper.lm.model}."
        return dspy.Prediction(
            **subtopics,
            probabilities=probabilities,
            model=mapper.lm.model,
            dedicated=is_dedicated_decision_model(mapper.lm),
            reasoning=reasoning,
        )
