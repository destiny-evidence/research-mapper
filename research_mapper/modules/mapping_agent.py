import asyncio

import dspy

from research_mapper.factory import mapping_along_dimensions_signature_builder
from research_mapper.models import (
    Evidence,
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
        return asyncio.run(self.aforward(user_query, evidence))

    async def aforward(
        self, user_query: UserQuery, evidence: list[Evidence]
    ) -> dspy.Prediction:
        suggested_dimensions = self._generate_suggested_dimensions(user_query)
        finalised_dimensions = self._validate_dimensions(suggested_dimensions)
        suggested_subtopics = await self._generate_dimension_subtopics(
            user_query, finalised_dimensions
        )
        finalised_subtopics = self._validate_dimension_subtopics(suggested_subtopics)
        mapping = await self._generate_evidence_map(
            user_query, finalised_subtopics, evidence
        )
        return mapping

    def _generate_suggested_dimensions(
        self, user_query: UserQuery
    ) -> tuple[MappingDimension, MappingDimension, MappingDimension]:
        if self.tui is not None:
            with LiveAgentPanel(user_query.query, self.tui) as panel_ui:
                dimensions = read_reasoning_stream(
                    program=self.mapping_dimension_generator,
                    original_query=user_query,
                    on_chunk=panel_ui.get_callback_for_buffer(user_query.query),
                ).dimensions

            self.tui.print_info(
                "[green]✓[/green] Mapping dimensions generated successfully!"
            )
        else:
            dimensions = self.mapping_dimension_generator(
                original_query=user_query
            ).dimensions
        return dimensions

    def _validate_dimensions(
        self, dimensions: tuple[MappingDimension, MappingDimension, MappingDimension]
    ) -> tuple[MappingDimension, MappingDimension, MappingDimension]:
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
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        if self.tui is not None:
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
    ):
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
        return [
            MappedEvidence(
                evidence=e,
                coordinate=dict(zip(dimension_names, pred.mapping_coordinate)),
            )
            for e, pred in zip(evidence, results)
        ]
