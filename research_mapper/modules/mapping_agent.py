import asyncio

import dspy

from research_mapper.factory import mapping_along_dimensions_signature_builder
from research_mapper.models import (
    Evidence,
    EvidenceMap,
    MappedEvidence,
    UserQuery,
    MappingDimension,
    MappingDimensionWithSubTopics,
)
from research_mapper.modules.utils import (
    MAX_CONCURRENCY,
    read_reasoning_stream,
    run_with_semaphore,
)
from research_mapper.signatures import (
    EvidenceMappingDimensionsFromQuery,
    SubtopicFromEvidenceMappingDimension,
)
from research_mapper.ui import TerminalUI, LiveAgentPanel, LiveAgentPanels


class MappingAgent(dspy.Module):
    """
    An agent to map Evidence objects across 3 dimensions.
    """

    def __init__(self, tui: TerminalUI | None = None) -> None:
        self.mapping_dimension_generator = dspy.ChainOfThought(
            EvidenceMappingDimensionsFromQuery
        )
        self.dimension_subtopics_generator = dspy.ChainOfThought(
            SubtopicFromEvidenceMappingDimension
        )
        self.tui = tui

    def forward(
        self, user_query: UserQuery, evidence: list[Evidence]
    ) -> dspy.Prediction:
        """
        Implements DSPy Module's forward method by wrapping the aforward one.
        :param user_query: the user query the evidence is being mapped for
        :param evidence: the collection of Evidence objects to map
        :return: a DSPy Prediction wrapping an EvidenceMap
        """
        return asyncio.run(self.aforward(user_query, evidence))

    async def aforward(
        self, user_query: UserQuery, evidence: list[Evidence]
    ) -> dspy.Prediction:
        """
        Generates mapping dimensions and their subtopics, validates them by the user, and maps each
        piece of evidence to a coordinate across those dimensions.
        :param user_query: the user query the evidence is being mapped for
        :param evidence: the collection of Evidence objects to map
        :return: a DSPy Prediction wrapping an EvidenceMap
        """
        suggested_dimensions = self._generate_suggested_dimensions(user_query)
        finalised_dimensions = self._validate_dimensions(suggested_dimensions)
        suggested_subtopics = await self._generate_dimension_subtopics(
            user_query, finalised_dimensions
        )
        final_dims_with_subtopics = self._validate_dimension_subtopics(
            suggested_subtopics
        )
        mapping = await self._generate_evidence_map(
            user_query, final_dims_with_subtopics, evidence
        )
        evidence_map = EvidenceMap(
            mapped_evidence=mapping, dimensions=final_dims_with_subtopics
        )
        return dspy.Prediction(evidence_map=evidence_map)

    def _generate_suggested_dimensions(
        self, user_query: UserQuery
    ) -> tuple[MappingDimension, MappingDimension, MappingDimension]:
        """
        Generates 3 suggested dimensions to map evidence across for a user's query.
        :param user_query: the user's original query to generate mapping dimensions for
        :return: the 3 suggested mapping dimensions
        """
        if self.tui is not None:
            with LiveAgentPanel(user_query.query, self.tui) as panel_ui:
                prediction = read_reasoning_stream(
                    program=self.mapping_dimension_generator,
                    original_query=user_query,
                    on_chunk=panel_ui.get_callback_for_buffer(user_query.query),
                )

            self.tui.print_info(
                "[green]✓[/green] Mapping dimensions generated successfully!"
            )
        else:
            prediction = self.mapping_dimension_generator(original_query=user_query)
        return (prediction.dimension1, prediction.dimension2, prediction.dimension3)

    def _validate_dimensions(
        self, dimensions: tuple[MappingDimension, MappingDimension, MappingDimension]
    ) -> tuple[MappingDimension, MappingDimension, MappingDimension]:
        """
        Validates suggested mapping dimensions via the user when UI available. Accepts them all if not.
        :param dimensions: the suggested mapping dimensions to be validated
        :return: the finalised mapping dimensions
        """
        if self.tui is None:
            return dimensions
        finalised = self.tui.confirm_or_replace(
            dimensions, title="Suggested mapping dimensions", noun="dimensions"
        )
        return tuple(finalised)

    async def _generate_dimension_subtopics(
        self,
        user_query: UserQuery,
        dimensions: tuple[MappingDimension, MappingDimension, MappingDimension],
    ) -> tuple[
        MappingDimensionWithSubTopics,
        MappingDimensionWithSubTopics,
        MappingDimensionWithSubTopics,
    ]:
        """
        Asynchronously generates suggested subtopics for each mapping dimension.
        :param user_query: the user's original query for context
        :param dimensions: the mapping dimensions to generate subtopics for
        :return: the mapping dimensions, each upgraded with their suggested subtopics
        """
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        if self.tui is not None:
            self.tui.print_info("Generating suggested subtopics for each dimension:")
            with LiveAgentPanels(dimensions, self.tui) as panel_ui:
                results = await asyncio.gather(
                    *[
                        run_with_semaphore(
                            read_reasoning_stream,
                            semaphore,
                            program=self.dimension_subtopics_generator,
                            original_query=user_query,
                            other_dimensions=list(dimensions[:i] + dimensions[i + 1 :]),
                            dimension=dim,
                            on_chunk=panel_ui.get_callback_for_buffer(dim),
                        )
                        for i, dim in enumerate(dimensions)
                    ]
                )

            self.tui.print_info(
                "[green]✓[/green] Subtopics for each dimension generated successfully!"
            )
        else:
            results = await asyncio.gather(
                *[
                    run_with_semaphore(
                        self.dimension_subtopics_generator,
                        semaphore,
                        original_query=user_query,
                        other_dimensions=list(dimensions[:i] + dimensions[i + 1 :]),
                        dimension=dim,
                    )
                    for i, dim in enumerate(dimensions)
                ]
            )
        return tuple(
            MappingDimensionWithSubTopics(
                **mapping_dim.model_dump(), subtopics=pred.subtopics
            )
            for mapping_dim, pred in zip(dimensions, results)
        )

    def _validate_dimension_subtopics(
        self,
        dimensions: tuple[
            MappingDimensionWithSubTopics,
            MappingDimensionWithSubTopics,
            MappingDimensionWithSubTopics,
        ],
    ) -> tuple[
        MappingDimensionWithSubTopics,
        MappingDimensionWithSubTopics,
        MappingDimensionWithSubTopics,
    ]:
        """
        Validates suggested dimension subtopics via the user when UI available. Accepts them all if
        not. Re-prompts for a dimension if the user drops all of its subtopics, since each dimension
        must retain at least one.
        :param dimensions: the mapping dimensions with suggested subtopics to be validated
        :return: the mapping dimensions with finalised subtopics
        """
        if self.tui is None:
            return dimensions
        finalised_dimensions = tuple()
        for dim in dimensions:
            while True:
                finalised_subtopics = self.tui.confirm_or_replace(
                    dim.subtopics,
                    title=f"Suggested subtopics for '{dim.name}' dimension",
                    noun="subtopics",
                    allow_drop=True,
                )
                if finalised_subtopics:
                    break
                self.tui.print_info(
                    f"[red]'{dim.name}' must have at least one subtopic — try again.[/red]"
                )
            finalised_dimensions += (
                MappingDimensionWithSubTopics(
                    **dim.model_dump(exclude={"subtopics"}),
                    subtopics=finalised_subtopics,
                ),
            )
        return finalised_dimensions

    async def _generate_evidence_map(
        self,
        user_query: UserQuery,
        dimensions: tuple[
            MappingDimensionWithSubTopics,
            MappingDimensionWithSubTopics,
            MappingDimensionWithSubTopics,
        ],
        evidence: list[Evidence],
    ) -> list[MappedEvidence]:
        """
        Asynchronously maps each piece of evidence to a coordinate across the provided dimensions
        and their subtopics.
        :param user_query: the user's original query for context
        :param dimensions: the finalised mapping dimensions, each with their finalised subtopics
        :param evidence: the Evidence objects to be mapped
        :return: the collection of MappedEvidence objects
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
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        if self.tui is not None:
            self.tui.print_info("Mapping evidence across dimensions:")
            with LiveAgentPanels(evidence, self.tui) as panel_ui:
                results = await asyncio.gather(
                    *[
                        run_with_semaphore(
                            read_reasoning_stream,
                            semaphore,
                            program=map_evidence_along_dimensions,
                            original_query=user_query,
                            evidence=piece_of_evidence,
                            dimensions=dimensions,
                            on_chunk=panel_ui.get_callback_for_buffer(
                                piece_of_evidence
                            ),
                        )
                        for piece_of_evidence in evidence
                    ]
                )
            self.tui.print_info("[green]✓[/green] Evidence mapped successfully!")
        else:
            results = await asyncio.gather(
                *[
                    run_with_semaphore(
                        map_evidence_along_dimensions,
                        semaphore,
                        original_query=user_query,
                        evidence=piece_of_evidence,
                        dimensions=dimensions,
                    )
                    for piece_of_evidence in evidence
                ]
            )
        dimension_names = [dim.name for dim in dimensions]
        subtopic_fields = (
            "dimension1_subtopic",
            "dimension2_subtopic",
            "dimension3_subtopic",
        )
        return [
            MappedEvidence(
                evidence=e,
                coordinate=dict(
                    zip(
                        dimension_names,
                        (getattr(pred, field) for field in subtopic_fields),
                    )
                ),
            )
            for e, pred in zip(evidence, results)
        ]
