import asyncio

import dspy

from research_mapper.models import Evidence, UserQuery, ScreeningCriterion
from research_mapper.modules.utils import read_reasoning_stream
from research_mapper.signatures import (
    UserQueryToScreeningCriteria,
    ScreenEvidenceUsingCriteria,
)
from research_mapper.ui import TerminalUI, LiveAgentPanel


class ScreeningAgent(dspy.Module):
    def __init__(self, tui: TerminalUI | None = None):
        self.screening_criteria_generator = dspy.ChainOfThought(
            UserQueryToScreeningCriteria
        )
        self.evidence_screener = dspy.ChainOfThought(ScreenEvidenceUsingCriteria)
        self.tui = tui

    def forward(
        self, user_query: UserQuery, evidence: list[Evidence]
    ) -> dspy.Prediction:
        return asyncio.run(self.aforward(user_query, evidence))

    async def aforward(
        self, user_query: UserQuery, evidence: list[Evidence]
    ) -> dspy.Prediction:
        screening_criteria = self._generate_screening_criteria(user_query)
        screening_criteria = self._filter_screening_criteria(screening_criteria)
        screened_evidence = await self._screen_evidence(screening_criteria, evidence)
        return dspy.Prediction(screened_evidence=screened_evidence)

    def _generate_screening_criteria(
        self, user_query: UserQuery
    ) -> list[ScreeningCriterion]:
        if self.tui is not None:
            with LiveAgentPanel(user_query.query, self.tui) as panel_ui:
                screening_criteria = read_reasoning_stream(
                    program=self.screening_criteria_generator,
                    original_query=user_query.query,
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
        if self.tui is not None:
            return self.tui.select_from_list(
                screening_criteria, title="Suggested screening criteria"
            )
        else:
            return screening_criteria

    async def _screen_evidence(
        self, screening_criteria: list[ScreeningCriterion], evidence: list[Evidence]
    ) -> list[Evidence]:
        if self.tui is not None:
            with LiveAgentPanel(evidence, self.tui) as panel_ui:
                results = await asyncio.gather(
                    *[
                        asyncio.to_thread(
                            read_reasoning_stream,
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
                    asyncio.to_thread(
                        self.evidence_screener,
                        evidence=piece_of_evidence,
                        screening_criteria=screening_criteria,
                    )
                    for piece_of_evidence in evidence
                ]
            )

        return [evid for evid, pred in zip(evidence, results) if pred.include]
