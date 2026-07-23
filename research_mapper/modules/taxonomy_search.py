import dspy

from research_mapper.models.common import UserQuery
from research_mapper.models.taxonomy_search import Concept
from research_mapper.signatures.taxonomy_search import (
    TaxonomyConceptFiltersFromUserQuery,
)
from research_mapper.tools.taxonomy_search import (
    ConceptFilterGenerationTools,
)
from research_mapper.ui.tui import TerminalUI


class TaxonomyConceptFilterGenerator(dspy.Module):
    """
    Generates a set of taxonomy concepts to filter references with.
    """

    def __init__(self, ui: TerminalUI | None = None) -> None:
        tools = []
        if ui is not None:
            filter_generation_tools = ConceptFilterGenerationTools(ui)
            tools = [
                filter_generation_tools.ask_for_clarification,
                filter_generation_tools.ask_for_disambiguation,
            ]
        self.agent = dspy.ReAct(
            signature=TaxonomyConceptFiltersFromUserQuery,
            tools=tools,
            max_iters=5,
        )

    def forward(
        self, user_query: UserQuery, taxonomy_concepts: list[Concept]
    ) -> dspy.Prediction:
        """
        Runs an agent to interactively generate a set of concepts to filter references on.
        :param user_query: the original user query
        :param taxonomy_concepts: the collection of taxonomy/vocabulary concepts to generate filter groups with
        :return:  a Prediction wrapping a collection of ConceptFilterGroup instances
        """
        return self.agent(user_query=user_query, taxonomy_concepts=taxonomy_concepts)
