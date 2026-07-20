from itertools import chain

import dspy

from research_mapper.models import (
    UserQuery,
    Evidence,
    EvidenceMap,
    LuceneQuery,
    ScreeningCriterion,
)
from research_mapper.modules.screening import CriteriaGenerator, EvidenceScreener
from research_mapper.modules.sparse_search import (
    EvidenceRetriever,
    SparseQueryGenerator,
)
from research_mapper.modules.mapping_agent import MappingAgent
from research_mapper.modules.utils import MAX_CONCURRENCY
from research_mapper.ui import TerminalUI


class WorkflowAgent(dspy.Module):
    """
    A DSPy program/module for searching, screening, and mapping evidence/research for a user's query.
    """

    def __init__(self, tui: TerminalUI | None = None) -> None:
        self.tui = tui
        self.search_query_generator = SparseQueryGenerator()
        self.evidence_retriever = EvidenceRetriever()
        self.criteria_generator = CriteriaGenerator()
        self.evidence_screener = EvidenceScreener()
        self.mapping_agent = MappingAgent(tui=tui)

    def forward(self, user_query: UserQuery) -> dspy.Prediction:
        """
        Gathers, screens, and maps evidence for relevance to the user's query.
        :param user_query: the user query to map research for
        :return: a DSPy Prediction wrapping an EvidenceMap
        """
        evidence = self._gather_evidence(user_query)
        filtered_evidence = self._screen_evidence(user_query, evidence)
        evidence_map = self._map_evidence(user_query, filtered_evidence)
        return dspy.Prediction(evidence_map=evidence_map)

    def _gather_evidence(self, user_query: UserQuery) -> list[Evidence]:
        """
        Generates search queries, validates them by the user, and retrieves evidence for each.
        :param user_query: the user query to gather evidence for
        :return: a collection of potentially relevant evidence
        """
        search_queries = self._generate_search_queries(user_query)
        search_queries = self._filter_search_queries(search_queries)
        evidence = self._retrieve_evidence(user_query, search_queries)
        if self.tui:
            self.tui.print_info(
                f"{len(evidence)} pieces of evidence retrieved. Moving onto screening."
            )
        return evidence

    def _generate_search_queries(self, user_query: UserQuery) -> list[LuceneQuery]:
        """
        Generates a set of candidate Lucene queries to search the DESTINY repository with.
        :param user_query: the user's query to generate search queries for
        :return: a collection of Lucene search queries
        """
        prediction = self.search_query_generator(user_query=user_query)
        if self.tui:
            self.tui.print_reasoning("Search queries", prediction.reasoning)
        return prediction.search_queries

    def _filter_search_queries(
        self, search_queries: list[LuceneQuery]
    ) -> list[LuceneQuery]:
        """
        Filters suggested search queries via the user when a UI is available. Accepts all if not.
        :param search_queries: the suggested search queries to be filtered
        :return: the filtered search queries
        """
        if self.tui is None:
            return search_queries
        return self.tui.select_from_list(
            search_queries, title="Suggested search queries"
        )

    def _retrieve_evidence(
        self, user_query: UserQuery, search_queries: list[LuceneQuery]
    ) -> list[Evidence]:
        """
        Dispatches subagents for each search query to retrieve evidence from the DESTINY
        repository, in parallel.
        :param user_query: the original user query, for context
        :param search_queries: the search queries to retrieve evidence for
        :return: a set of unique Evidence objects
        """
        examples = [
            dspy.Example(user_query=user_query, search_query=search_query).with_inputs(
                "user_query", "search_query"
            )
            for search_query in search_queries
        ]
        results = self.evidence_retriever.batch(examples, num_threads=MAX_CONCURRENCY)
        if self.tui:
            for search_query, prediction in zip(search_queries, results):
                self.tui.print_reasoning(str(search_query), prediction.reasoning)
        return list(
            set(chain.from_iterable(prediction.evidence for prediction in results))
        )

    def _screen_evidence(
        self, user_query: UserQuery, evidence: list[Evidence]
    ) -> list[Evidence]:
        """
        Generates screening criteria, validates them by the user, and screens the given evidence
        against them.
        :param user_query: the user query to screen evidence for
        :param evidence: evidence to screen for relevance
        :return: a collection of screened evidence
        """
        screening_criteria = self._generate_screening_criteria(user_query)
        screening_criteria = self._filter_screening_criteria(screening_criteria)
        filtered_evidence = self._run_screening(screening_criteria, evidence)
        if self.tui:
            self.tui.print_info(
                f"{len(evidence) - len(filtered_evidence)} piece(s) of evidence removed during screening. {len(filtered_evidence)} piece(s) of evidence remaining."
            )
        return filtered_evidence

    def _generate_screening_criteria(
        self, user_query: UserQuery
    ) -> list[ScreeningCriterion]:
        """
        Generates a set of inclusion and exclusion screening criteria.
        :param user_query: the original user's query to generate screening criteria for
        :return: a list of ScreeningCriterion objects to consider
        """
        prediction = self.criteria_generator(user_query=user_query)
        if self.tui:
            self.tui.print_reasoning("Screening criteria", prediction.reasoning)
        return prediction.screening_criteria

    def _filter_screening_criteria(
        self, screening_criteria: list[ScreeningCriterion]
    ) -> list[ScreeningCriterion]:
        """
        Filters suggested screening criteria via the user when a UI is available. Accepts all
        criteria if not.
        :param screening_criteria: the suggested screening criteria to be filtered
        :return: a list of filtered screening criteria
        """
        if self.tui is None:
            return screening_criteria
        return self.tui.select_from_list(
            screening_criteria, title="Suggested screening criteria"
        )

    def _run_screening(
        self,
        screening_criteria: list[ScreeningCriterion],
        evidence: list[Evidence],
    ) -> list[Evidence]:
        """
        Screens each piece of evidence against the given screening criteria, in parallel.
        :param screening_criteria: the screening criteria to screen evidence against
        :param evidence: the Evidence objects to be screened
        :return: the collection of evidence to include
        """
        examples = [
            dspy.Example(
                evidence=piece_of_evidence, screening_criteria=screening_criteria
            ).with_inputs("evidence", "screening_criteria")
            for piece_of_evidence in evidence
        ]
        results = self.evidence_screener.batch(examples, num_threads=MAX_CONCURRENCY)
        if self.tui:
            for piece_of_evidence, prediction in zip(evidence, results):
                self.tui.print_reasoning(str(piece_of_evidence), prediction.reasoning)
        return [
            piece_of_evidence
            for piece_of_evidence, prediction in zip(evidence, results)
            if prediction.include
        ]

    def _map_evidence(
        self, user_query: UserQuery, filtered_evidence: list[Evidence]
    ) -> EvidenceMap:
        """
        Maps screened evidence across mapping dimensions and their subtopics using a MappingAgent.
        :param user_query: the user query the evidence is being mapped for
        :param filtered_evidence: the screened evidence to map
        :return: an EvidenceMap of the screened evidence
        """
        if self.tui:
            self.tui.print_info("Generating suggested dimensions to map across:")

        return self.mapping_agent(user_query, filtered_evidence).evidence_map
