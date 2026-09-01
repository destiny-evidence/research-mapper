"""Building the map and placing evidence on it."""

import builtins
import logging
from typing import ClassVar, Protocol

import dspy
from pydantic import BaseModel

from research_mapper.engine.context import StepContext
from research_mapper.engine.registry import Step
from research_mapper.engine.views import AskSpec
from research_mapper.models.common import UserQuery
from research_mapper.models.mapping import (
    DimensionSubTopic,
    MappingDimension,
    MappingDimensionWithSubTopics,
)
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.context import EvidenceMapContext
from research_mapper.workflows.evidence_map.fanout import ProgressTracker
from research_mapper.workflows.evidence_map.hydrate import get_evidence
from research_mapper.workflows.evidence_map.pipeline import (
    DimensionGenerator,
    EvidenceMapper,
    SubtopicGenerator,
)
from research_mapper.workflows.evidence_map.views import CoordinateRow

logger = logging.getLogger(__name__)

SUBTOPICS = "generating subtopics"
MAPPING = "mapping evidence"


class NothingToMap(Exception):
    """Screening included nothing, so the map would be empty."""


SUBTOPIC_FIELDS = (
    "dimension1_subtopic",
    "dimension2_subtopic",
    "dimension3_subtopic",
)


class Subtopics(Protocol):
    """What the subtopic generator put on a Prediction."""

    subtopics: list[DimensionSubTopic]


class GenerateMapDimensionsParams(BaseModel):
    """Inputs to generate_map_dimensions."""

    regenerate: bool = False


class GenerateMapDimensions(Step[GenerateMapDimensionsParams, StepContext]):
    """Suggest the axes to map evidence across and keep the user's edits."""

    type: ClassVar[str] = "generate_map_dimensions"
    Params: ClassVar[builtins.type[BaseModel]] = GenerateMapDimensionsParams

    def run(self, ctx: StepContext, params: GenerateMapDimensionsParams) -> dict:
        """Suggest three mapping dimensions, then keep the user's edited set."""

        def generate() -> artifacts.MapDimensions:
            prediction = DimensionGenerator()(
                user_query=UserQuery(query=ctx.research_session.question)
            )
            return artifacts.MapDimensions(
                dimensions=[
                    prediction.dimension1,
                    prediction.dimension2,
                    prediction.dimension3,
                ],
                reasoning=prediction.reasoning,
            )

        suggested = ctx.get_or_generate_artifact(
            artifacts.SUGGESTED_MAP_DIMENSIONS, generate, params.regenerate
        )

        chosen = ctx.ask(
            "edit_dimensions",
            AskSpec(
                type="edit_list",
                prompt="Edit the dimensions to map the evidence across.",
                options=[
                    {
                        "id": str(i),
                        "label": str(dimension),
                        "value": dimension.model_dump(mode="json"),
                    }
                    for i, dimension in enumerate(suggested.dimensions)
                ],
                constraints={
                    "min": artifacts.DIMENSION_COUNT,
                    "max": artifacts.DIMENSION_COUNT,
                    "allow_new": True,
                },
            ),
        )

        version = ctx.write_artifact(
            artifacts.MAP_DIMENSIONS,
            artifacts.MapDimensions.model_validate(
                {"dimensions": chosen, "reasoning": suggested.reasoning}
            ),
        )
        return {"dimensions": len(chosen), "version": version}


class GenerateMapSubtopicsParams(BaseModel):
    """Inputs to generate_map_subtopics."""

    regenerate: bool = False


class GenerateMapSubtopics(Step[GenerateMapSubtopicsParams, StepContext]):
    """Suggest subtopics for each chosen dimension and keep the user's edits."""

    type: ClassVar[str] = "generate_map_subtopics"
    Params: ClassVar[builtins.type[BaseModel]] = GenerateMapSubtopicsParams

    def run(self, ctx: StepContext, params: GenerateMapSubtopicsParams) -> dict:
        """Suggest subtopics per dimension, then keep the user's edited sets."""
        dimensions = ctx.require_artifact(artifacts.MAP_DIMENSIONS).dimensions

        def generate() -> artifacts.Dimensions:
            suggested, reasoning = self._suggest(ctx, dimensions)
            return artifacts.Dimensions(
                dimensions=suggested, subtopic_reasoning=reasoning
            )

        suggested = ctx.get_or_generate_artifact(
            artifacts.SUGGESTED_DIMENSION_SUBTOPICS, generate, params.regenerate
        )

        answers = ctx.ask_all(
            {
                _key(dimension): AskSpec(
                    type="edit_list",
                    prompt=f"Edit the subtopics of {dimension.name}.",
                    options=[
                        {
                            "id": str(i),
                            "label": subtopic.name,
                            "value": subtopic.model_dump(mode="json"),
                        }
                        for i, subtopic in enumerate(dimension.subtopics)
                    ],
                    constraints={"min": 1, "allow_new": True},
                )
                for dimension in suggested.dimensions
            }
        )

        edited = [
            MappingDimensionWithSubTopics(
                name=dimension.name,
                description=dimension.description,
                subtopics=[
                    DimensionSubTopic.model_validate(subtopic)
                    for subtopic in answers[_key(dimension)]
                ],
            )
            for dimension in suggested.dimensions
        ]
        version = ctx.write_artifact(
            artifacts.DIMENSIONS,
            artifacts.Dimensions(
                dimensions=edited,
                reasoning=suggested.reasoning,
                subtopic_reasoning=suggested.subtopic_reasoning,
            ),
        )
        return {
            "dimensions": len(edited),
            "subtopics": sum(len(dimension.subtopics) for dimension in edited),
            "version": version,
        }

    def _suggest(
        self, ctx: StepContext, dimensions: list[MappingDimension]
    ) -> tuple[list[MappingDimensionWithSubTopics], dict[str, str]]:
        """Generate subtopics for every dimension at once."""
        user_query = UserQuery(query=ctx.research_session.question)
        examples = [
            dspy.Example(
                user_query=user_query,
                dimension=dimension,
                other_dimensions=[
                    other for other in dimensions if other.name != dimension.name
                ],
            ).with_inputs("user_query", "dimension", "other_dimensions")
            for dimension in dimensions
        ]
        tracker = ProgressTracker(ctx, len(examples), note=SUBTOPICS)
        tracker.start()
        predictions: list[Subtopics | None] = tracker.fan_out(
            SubtopicGenerator(), examples
        )

        suggested = []
        reasoning: dict[str, str] = {}
        for dimension, prediction in zip(dimensions, predictions, strict=True):
            if prediction is None:
                msg = f"no subtopics were generated for {dimension.name}"
                raise RuntimeError(msg)
            suggested.append(
                MappingDimensionWithSubTopics(
                    name=dimension.name,
                    description=dimension.description,
                    subtopics=prediction.subtopics,
                )
            )
            reasoning[dimension.name] = getattr(prediction, "reasoning", "") or ""
        return suggested, reasoning


class GenerateMapParams(BaseModel):
    """Inputs to generate_map."""


class GenerateMap(Step[GenerateMapParams, EvidenceMapContext]):
    """Map every included reference to a coordinate across the finalised dimensions."""

    type: ClassVar[str] = "generate_map"
    Params: ClassVar[builtins.type[BaseModel]] = GenerateMapParams

    def run(self, ctx: EvidenceMapContext, params: GenerateMapParams) -> dict:
        """Place each included reference on the map."""
        dimensions = ctx.require_artifact(artifacts.DIMENSIONS).dimensions
        if len(dimensions) != artifacts.DIMENSION_COUNT:
            msg = (
                f"a map needs {artifacts.DIMENSION_COUNT} dimensions, "
                f"this one has {len(dimensions)}"
            )
            raise ValueError(msg)
        dimensions_version = ctx.get_artifact_version(artifacts.DIMENSIONS)
        references = ctx.references_to_map(dimensions_version)
        already_mapped = ctx.count_mapped_at(dimensions_version)
        if not references and not already_mapped:
            msg = "screening included no evidence, so there is nothing to map"
            raise NothingToMap(msg)

        user_query = UserQuery(query=ctx.research_session.question)
        axes = (dimensions[0], dimensions[1], dimensions[2])
        tracker = ProgressTracker(
            ctx, len(references) + already_mapped, note=MAPPING, done=already_mapped
        )
        tracker.start()

        mapped = 0
        for evidence_page in get_evidence([r.destiny_id for r in references]):
            evidence = evidence_page.values()
            examples = [
                dspy.Example(
                    user_query=user_query, evidence=item, dimensions=axes
                ).with_inputs("user_query", "evidence", "dimensions")
                for item in evidence
            ]
            predictions = tracker.fan_out(EvidenceMapper(), examples)

            rows: list[CoordinateRow] = []
            for item, prediction in zip(evidence, predictions, strict=True):
                if prediction is None:
                    logger.warning("mapping failed for id %s", item.destiny_id)
                    continue
                rows.append(
                    CoordinateRow(
                        destiny_id=item.destiny_id,
                        coordinate={
                            dimension.name: [getattr(prediction, field)]
                            for dimension, field in zip(
                                dimensions, SUBTOPIC_FIELDS, strict=True
                            )
                        },
                        reasoning=prediction.reasoning,
                        dimensions_version=dimensions_version or 1,
                    )
                )
            ctx.set_coordinates(rows)
            mapped += len(rows)

        return {"mapped": mapped, "failed": tracker.failed}


def _key(dimension: MappingDimension) -> str:
    """The decision key for one dimension's subtopics."""
    return f"edit_subtopics:{dimension.name}"
