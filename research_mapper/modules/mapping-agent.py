import dspy

from research_mapper.models import (
    Evidence,
    UserQuery,
    MappingDimension,
)
from research_mapper.modules.utils import read_reasoning_stream
from research_mapper.signatures import (
    EvidenceMappingDimensionsFromQuery,
    SubtopicFromEvidenceMappingDimension,
)
from research_mapper.ui import TerminalUI, LiveAgentPanel


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

    def forward(self):
        pass

    def aforward(self, user_query: UserQuery, evidence: list[Evidence]):
        suggested_dimensions = self._generate_suggested_dimensions(user_query)
        finalised_dimensions = self._validate_dimensions(suggested_dimensions)
        suggested_subtopics = self._generate_dimension_subtopics(finalised_dimensions)
        finalised_subtopics = self._validate_dimension_subtopics(suggested_subtopics)
        mapping = self._generate_evidence_map(finalised_dimensions, finalised_subtopics)
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

    def _generate_dimension_subtopics(self):
        pass

    def _validate_dimension_subtopics(self):
        pass

    def _generate_evidence_map(self):
        self.mapping_coordinate_predictor = dspy.ChainOfThought()
        pass
