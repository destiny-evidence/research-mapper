import dspy

from research_mapper.models import UserQuery, Evidence
from research_mapper.modules.screening_agent import ScreeningAgent
from research_mapper.modules.search_agent import SearchAgent
from research_mapper.modules.mapping_agent import MappingAgent
from research_mapper.ui import TerminalUI


class WorkflowAgent(dspy.Module):
    """
    A DSPy program/module for searching, screening, and mapping evidence/research for a user's query.
    """

    def __init__(self, tui: TerminalUI | None = None) -> None:
        self.tui = tui
        self.search_agent = SearchAgent(tui=tui)
        self.screening_agent = ScreeningAgent(tui=tui)
        self.mapping_agent = MappingAgent(tui=tui)

    def forward(self, user_query: UserQuery) -> dspy.Prediction:
        """
        Gathers and screens evidence for relevance to the user's query.
        :param user_query: the user query to map research for
        :return: a DSPy Prediction wrapping a collection of screened evidence
        """
        evidence = self._gather_evidence(user_query)
        filtered_evidence = self._screen_evidence(user_query, evidence)
        mapped_evidence = self.mapping_agent(user_query, filtered_evidence)
        return dspy.Prediction(evidence_map=mapped_evidence)

    def _gather_evidence(self, user_query: UserQuery) -> list[Evidence]:
        """
        Gathers evidence for a user's query using a SearchAgent.
        :param user_query: the user query to gather evidence for
        :return: a collection of potentially relevant evidence
        """
        if self.tui:
            self.tui.print_info("Generating suggested search queries:")
            evidence = self.search_agent(user_query=user_query).evidence
            self.tui.print_info(
                f"{len(evidence)} pieces of evidence retrieved. Moving onto screening."
            )
        else:
            evidence = self.search_agent(user_query=user_query).evidence
        return evidence

    def _screen_evidence(
        self, user_query: UserQuery, evidence: list[Evidence]
    ) -> list[Evidence]:
        """
        Screens evidence for relevance to the user's query using a ScreeningAgent.
        :param user_query: the user query to screen evidence for
        :param evidence: evidence to screen for relevance
        :return: a collection of screened evidence
        """
        filtered_evidence = self.screening_agent(
            user_query=user_query, evidence=evidence
        ).screened_evidence
        if self.tui:
            self.tui.print_info(
                f"{len(evidence) - len(filtered_evidence)} piece(s) of evidence removed during screening. {len(filtered_evidence)} piece(s) of evidence remaining."
            )
        return filtered_evidence
