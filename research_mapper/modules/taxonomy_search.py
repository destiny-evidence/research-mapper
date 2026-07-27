import logging

import dspy

from research_mapper.models.common import UserQuery
from research_mapper.models.taxonomy_search import Concept, ConceptFilterGroup
from research_mapper.signatures.taxonomy_search import (
    GatherEvidenceFromConceptFilters,
    TaxonomyConceptFiltersFromUserQuery,
)
from research_mapper.taxonomy import RepoCommunity
from research_mapper.tools.taxonomy_search import (
    ConceptFilterGenerationTools,
    RetrieveEvidenceByConceptsTool,
    UnsatisfiabilityTool,
)
from research_mapper.ui.tui import TerminalUI

logger = logging.getLogger(__name__)


class TaxonomyConceptFilterGenerator(dspy.Module):
    """
    Generates a set of taxonomy concepts to filter references with.
    """

    def __init__(self, ui: TerminalUI | None = None) -> None:
        tools = []
        if ui is not None:
            filter_generation_tools = ConceptFilterGenerationTools(ui)
            tools.append(filter_generation_tools.ask_for_clarification)
        self._unsatisfiability_tool = UnsatisfiabilityTool()
        tools.append(self._unsatisfiability_tool.mark_unsatisfiable)
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
        :return: a Prediction wrapping a collection of ConceptFilterGroup instances, plus
            unsatisfiable_reason (None unless the agent flagged the query as unsatisfiable)
        """
        # self.agent/self._unsatisfiability_tool are built once and reused across calls
        # (that's what makes run_with_status's live streaming work here), so any reason
        # left over from a previous call must be cleared before this one runs.
        self._unsatisfiability_tool.reason = None
        prediction = self.agent(
            user_query=user_query, taxonomy_concepts=taxonomy_concepts
        )
        return dspy.Prediction(
            filter_groups=prediction.filter_groups,
            reasoning=prediction.reasoning,
            unsatisfiable_reason=self._unsatisfiability_tool.reason,
        )


class ConceptEvidenceRetriever(dspy.Module):
    """
    Dispatches a DSPy subagent to retrieve Evidence from the DESTINY repository for a
    fixed set of concept filters, deciding pagination/stopping itself.
    """

    def forward(
        self,
        user_query: UserQuery,
        community: RepoCommunity,
        filter_groups: list[ConceptFilterGroup],
        concepts: list[str | list[str]],
    ) -> dspy.Prediction:
        """
        Retrieves Evidence for a fixed set of concept filters.
        :param user_query: the original user query, for context
        :param community: the repository community to retrieve evidence from
        :param filter_groups: the concept filters, for the subagent's context
        :param concepts: the concept filters resolved to IRIs, to fix the retrieval tool with
        :return: a Prediction wrapping the retrieved evidence, alongside the subagent's
            search_summary, stopping_reason, and reasoning
        """
        tool = RetrieveEvidenceByConceptsTool(community, concepts)
        subagent = dspy.ReAct(
            signature=GatherEvidenceFromConceptFilters,
            tools=[tool.retrieve_evidence],
            max_iters=5,
        )
        prediction = subagent(original_query=user_query, filter_groups=filter_groups)

        logger.info("Found %d new items for concept filters", len(tool.retrieved))
        logger.debug("Search summary: %s", prediction.search_summary)
        logger.info('Agent stopped searching because: "%s"', prediction.stopping_reason)
        return dspy.Prediction(
            evidence=list(tool.retrieved.values()),
            search_summary=prediction.search_summary,
            stopping_reason=prediction.stopping_reason,
            reasoning=prediction.reasoning,
        )
