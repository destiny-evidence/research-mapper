import logging

import dspy
from rdflib import Graph

from research_mapper.models.common import UserQuery
from research_mapper.models.react import Step
from research_mapper.models.taxonomy_search import (
    ClarificationOptions,
    ConceptFilterGroup,
    IndexedVocab,
)
from research_mapper.modules.react import ResumableReAct
from research_mapper.signatures.taxonomy_search import (
    GatherEvidenceFromConceptFilters,
    TaxonomyConceptFiltersFromUserQuery,
)
from research_mapper.taxonomy import RepoCommunity
from research_mapper.tools.taxonomy_search import (
    RetrieveEvidenceByConceptsTool,
    TaxonomyBrowsingTools,
    ask_for_clarification,
    mark_unsatisfiable,
)
from research_mapper.ui.tui import TerminalUI

logger = logging.getLogger(__name__)

_NOT_SURE_OPTION = "I'm not sure"
_NONE_OF_THESE_OPTION = "None of these"
_SENTINEL_OPTIONS = {_NOT_SURE_OPTION, _NONE_OF_THESE_OPTION}


class TaxonomyConceptFilterGenerator(dspy.Module):
    """
    Generates a set of taxonomy concepts to filter references with, driving a
    ResumableReAct agent step by step so every reasoning step can be shown
    live, and so ask_for_clarification/mark_unsatisfiable can be answered or
    inspected by this caller before their (otherwise trivial) tool bodies
    ever run — neither tool touches the TUI or holds any state itself. The
    agent explores the taxonomy on demand via TaxonomyBrowsingTools rather
    than having it all handed to it upfront, so it's built fresh per call —
    its tools are bound to that call's community-specific indexed vocab/graph.
    """

    def __init__(self, ui: TerminalUI | None = None) -> None:
        self.ui = ui

    def forward(
        self, user_query: UserQuery, indexed: IndexedVocab, graph: Graph
    ) -> dspy.Prediction:
        """
        Runs an agent to interactively generate a set of concepts to filter references on.
        :param user_query: the original user query
        :param indexed: the community's indexed vocabulary, to explore via tool calls
        :param graph: the community's rdflib Graph, for broader/narrower lookups
        :return: a Prediction wrapping a collection of ConceptFilterGroup instances, plus
            unsatisfiable_reason (None unless the agent flagged the query as unsatisfiable)
        """
        self.agent = self._build_agent(indexed, graph)
        unsatisfiable_reason: str | None = None
        result = self.agent.start(user_query=user_query)
        while isinstance(result, Step):
            if self.ui is not None:
                self.ui.print_reasoning(f"Step {result.idx}", result.thought)
            if result.tool_name == "mark_unsatisfiable":
                unsatisfiable_reason = result.tool_args["reason"]
            elif result.tool_name == "ask_for_clarification" and self.ui is not None:
                answer = self._prompt_clarification(
                    ClarificationOptions(**result.tool_args["request"])
                )
                result = result.with_observation(answer)
            result = self.agent.resume(result, user_query=user_query)
        return dspy.Prediction(
            filter_groups=result.filter_groups,
            reasoning=result.reasoning,
            unsatisfiable_reason=unsatisfiable_reason,
        )

    def _build_agent(self, indexed: IndexedVocab, graph: Graph) -> ResumableReAct:
        browsing = TaxonomyBrowsingTools(graph, indexed)
        tools = [
            browsing.list_schemes,
            browsing.list_concepts_in_scheme,
            browsing.search_concepts,
            browsing.get_concept_detail,
            browsing.get_broader,
            browsing.get_narrower,
            mark_unsatisfiable,
        ]
        if self.ui is not None:
            tools.append(ask_for_clarification)
        return ResumableReAct(
            signature=TaxonomyConceptFiltersFromUserQuery,
            tools=tools,
            max_iters=50,
        )

    def _prompt_clarification(self, request: ClarificationOptions) -> list[str]:
        """
        Answers one proposed `ask_for_clarification` call by prompting the TUI. Only
        ever reached when `self.ui` is set — that's the only case `ask_for_clarification`
        is registered as a tool at all, so the agent can only propose it then.
        """
        options = [*request.options, _NONE_OF_THESE_OPTION, _NOT_SURE_OPTION]
        self.ui.print_info(request.question)
        while True:
            selected = self.ui.select_from_list(options, default=[len(options)])
            if len(selected) > 1 and _NONE_OF_THESE_OPTION in selected:
                self.ui.print_info(
                    '[red]"None of these" can\'t be combined '
                    "with other options — try again.[/red]"
                )
                continue
            return selected


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
