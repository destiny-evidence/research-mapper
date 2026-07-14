import asyncio

import dspy

from research_mapper.models import Evidence, UserQuery, ScreeningCriterion
from research_mapper.modules.utils import (
    MAX_CONCURRENCY,
    read_reasoning_stream,
    run_with_semaphore,
)
from research_mapper.signatures import (
    UserQueryToScreeningCriteria,
    ScreenEvidenceUsingCriteria,
)
from research_mapper.ui import TerminalUI, LiveAgentPanel, LiveAgentPanels


class ScreeningAgent(dspy.Module):
    """
    An agent to screen a collection of Evidence objects for relevance.
    """

    def __init__(self, tui: TerminalUI | None = None) -> None:
        self.screening_criteria_generator = dspy.ChainOfThought(
            UserQueryToScreeningCriteria
        )
        self.evidence_screener = dspy.ChainOfThought(ScreenEvidenceUsingCriteria)
        self.tui = tui

    def forward(
        self, user_query: UserQuery, evidence: list[Evidence]
    ) -> dspy.Prediction:
        """
        Implements DSPy Module's forward method by wrapping the aforward one.
        :param user_query: the user's original query to screen for
        :param evidence: the collection of Evidence objects to screen
        :return: a Prediction object wrapping a filtered collection of Evidence objects
        """
        return asyncio.run(self.aforward(user_query, evidence))

    async def aforward(
        self, user_query: UserQuery, evidence: list[Evidence]
    ) -> dspy.Prediction:
        """
        Generates screening criteria, validates them by the user, and asynchronously screens the Evidence objects.
        :param user_query: the user's original query to screen for
        :param evidence: the collection of Evidence objects to screen
        :return: a Prediction object wrapping a filtered collection of Evidence objects
        """
        screening_criteria = self._generate_screening_criteria(user_query)
        screening_criteria = self._filter_screening_criteria(screening_criteria)
        screened_evidence = await self._screen_evidence(screening_criteria, evidence)
        return dspy.Prediction(screened_evidence=screened_evidence)

    def _generate_screening_criteria(
        self, user_query: UserQuery
    ) -> list[ScreeningCriterion]:
        """
        Generates a set of inlcusion and exclusion screening criteria.
        :param user_query: the original user's query to generate screening criteria for
        :return: a list of ScreeningCriterion objects to consider
        """
        if self.tui is not None:
            with LiveAgentPanel(user_query.query, self.tui) as panel_ui:
                screening_criteria = read_reasoning_stream(
                    program=self.screening_criteria_generator,
                    original_query=user_query,
                    on_chunk=panel_ui.get_callback_for_buffer(user_query.query),
                ).screening_criteria

            self.tui.print_info(
                "[green]✓[/green] Screening criteria generated successfully!"
            )
        else:
            screening_criteria = self.screening_criteria_generator(
                original_query=user_query
            ).screening_criteria
        return screening_criteria

    def _filter_screening_criteria(
        self, screening_criteria: list[ScreeningCriterion]
    ) -> list[ScreeningCriterion]:
        """
        Filters potential screening criteria via the user when UI available. Accepts all criteria if not.
        :param screening_criteria: a list of screening criteria to be filtered
        :return: a list of filtered screening criteria
        """
        if self.tui is not None:
            return self.tui.select_from_list(
                screening_criteria, title="Suggested screening criteria"
            )
        else:
            return screening_criteria

    async def _screen_evidence(
        self, screening_criteria: list[ScreeningCriterion], evidence: list[Evidence]
    ) -> list[Evidence]:
        """
        Asynchronously screens Evidence objects using screening criteria.
        :param screening_criteria: the screening criteria to be used
        :param evidence: the Evidence objects to be screened
        :return: the collection of screened Evidence objects
        """
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        if self.tui is not None:
            with LiveAgentPanels(evidence, self.tui) as panel_ui:
                results = await asyncio.gather(
                    *[
                        run_with_semaphore(
                            read_reasoning_stream,
                            semaphore,
                            program=self.evidence_screener,
                            evidence=piece_of_evidence,
                            screening_criteria=screening_criteria,
                            on_chunk=panel_ui.get_callback_for_buffer(
                                piece_of_evidence
                            ),
                        )
                        for piece_of_evidence in evidence
                    ]
                )
            self.tui.print_info("[green]✓[/green] Evidence screened successfully!")
        else:
            results = await asyncio.gather(
                *[
                    run_with_semaphore(
                        self.evidence_screener,
                        semaphore,
                        evidence=piece_of_evidence,
                        screening_criteria=screening_criteria,
                    )
                    for piece_of_evidence in evidence
                ]
            )

        return [evid for evid, pred in zip(evidence, results) if pred.include]
