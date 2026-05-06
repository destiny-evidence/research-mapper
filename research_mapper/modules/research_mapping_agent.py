import dspy

from research_mapper.models import UserQuery, Evidence
from research_mapper.modules.screening_agent import ScreeningAgent
from research_mapper.modules.search_agent import SearchAgent
from research_mapper.ui import TerminalUI


class ResearchMappingAgent(dspy.Module):
    def __init__(self, tui: TerminalUI | None = None):
        self.tui = tui
        self.search_argent = SearchAgent(tui=tui)
        self.screening_agent = ScreeningAgent(tui=tui)

    def forward(self, user_query: UserQuery) -> dspy.Prediction:
        evidence = self._gather_evidence(user_query)
        filtered_evidence = self._screen_evidence(user_query, evidence)
        return dspy.Prediction(evidence=filtered_evidence)

    def _gather_evidence(self, user_query: UserQuery) -> list[Evidence]:
        if self.tui:
            self.tui.print_info("Generating suggested search queries:")
            evidence = self.search_argent(user_query=user_query).evidence
            self.tui.print_info(
                f"{len(evidence)} pieces of evidence retrieved. Moving onto screening."
            )
        else:
            evidence = self.search_argent(user_query=user_query).evidence
        return evidence

    def _screen_evidence(
        self, user_query: UserQuery, evidence: list[Evidence]
    ) -> list[Evidence]:
        filtered_evidence = self.screening_agent(
            user_query=user_query, evidence=evidence
        ).screened_evidence
        if self.tui:
            self.tui.print_info(
                f"{len(evidence) - len(filtered_evidence)} piece(s) of evidence removed during screening. {len(filtered_evidence)} piece(s) of evidence remaining."
            )
        return filtered_evidence
