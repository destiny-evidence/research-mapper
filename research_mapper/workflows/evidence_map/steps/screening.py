"""Deciding what stays in."""

import builtins
import logging
from itertools import batched
from typing import ClassVar, Protocol

import dspy
from pydantic import BaseModel

from research_mapper.config import reroll
from research_mapper.engine.registry import Step
from research_mapper.engine.views import AskSpec
from research_mapper.models.common import UserQuery
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.context import EvidenceMapContext
from research_mapper.workflows.evidence_map.enums import SessionReferenceStage
from research_mapper.workflows.evidence_map.fanout import (
    MAX_CONCURRENCY,
    ProgressTracker,
)
from research_mapper.workflows.evidence_map.hydrate import get_evidence
from research_mapper.workflows.evidence_map.pipeline import (
    CriteriaGenerator,
    EvidenceScreener,
)
from research_mapper.workflows.evidence_map.views import ScreeningRow

logger = logging.getLogger(__name__)

SCREENING = "screening evidence"


class NothingToScreen(Exception):
    """Screening was asked to run against a session that gathered no evidence."""


class GenerateScreeningCriteriaParams(BaseModel):
    """Inputs to generate_screening_criteria."""

    regenerate: bool = False


class GenerateScreeningCriteria(
    Step[GenerateScreeningCriteriaParams, EvidenceMapContext]
):
    """Generate a set of inclusion and exclusion screening criteria."""

    type: ClassVar[str] = "generate_screening_criteria"
    Params: ClassVar[builtins.type[BaseModel]] = GenerateScreeningCriteriaParams

    def run(
        self, ctx: EvidenceMapContext, params: GenerateScreeningCriteriaParams
    ) -> dict:
        """Suggest screening criteria, then keep the ones the user picks."""

        def generate(seed: int) -> artifacts.ScreeningCriteria:
            with reroll(seed):
                prediction = CriteriaGenerator()(
                    user_query=UserQuery(query=ctx.research_session.question)
                )
            return artifacts.ScreeningCriteria(
                criteria=prediction.screening_criteria, reasoning=prediction.reasoning
            )

        suggested = ctx.get_or_generate_artifact(
            artifacts.SUGGESTED_SCREENING_CRITERIA, generate, params.regenerate
        )

        chosen = ctx.ask(
            "select_criteria",
            AskSpec(
                type="select_many",
                prompt="Which of these criteria should we apply?",
                options=[
                    {
                        "id": str(i),
                        "label": str(criterion),
                        "value": criterion.model_dump(mode="json"),
                    }
                    for i, criterion in enumerate(suggested.criteria)
                ],
                constraints={"min": 1},
            ),
        )

        version = ctx.write_artifact(
            artifacts.SCREENING_CRITERIA,
            artifacts.ScreeningCriteria.model_validate(
                {"criteria": chosen, "reasoning": suggested.reasoning}
            ),
        )
        return {
            "suggested": len(suggested.criteria),
            "selected": len(chosen),
            "version": version,
        }


class ScreeningResult(Protocol):
    """What the screener put on a Prediction."""

    include: bool
    reasoning: str


class ScreenEvidenceParams(BaseModel):
    """Inputs to screen_evidence."""


class ScreenEvidence(Step[ScreenEvidenceParams, EvidenceMapContext]):
    """Screen evidence against the selected screening criteria."""

    type: ClassVar[str] = "screen_evidence"
    Params: ClassVar[builtins.type[BaseModel]] = ScreenEvidenceParams

    def run(self, ctx: EvidenceMapContext, params: ScreenEvidenceParams) -> dict:
        """Screen evidence against the selected screening criteria."""
        screening_criteria = ctx.require_artifact(artifacts.SCREENING_CRITERIA).criteria
        criteria_version = ctx.get_artifact_version(artifacts.SCREENING_CRITERIA)
        references = ctx.references(SessionReferenceStage.GATHERED)
        already_included_references = len(
            ctx.references(SessionReferenceStage.INCLUDED)
        )
        already_excluded_references = len(
            ctx.references(SessionReferenceStage.EXCLUDED)
        )
        total_references = (
            len(references) + already_included_references + already_excluded_references
        )
        if not total_references:
            msg = "no evidence was retrieved, so there is nothing to screen"
            raise NothingToScreen(msg)

        tracker = ProgressTracker(
            ctx,
            total=total_references,
            note=SCREENING,
            done=already_included_references + already_excluded_references,
        )
        tracker.start()
        included = already_included_references
        for evidence_page in get_evidence(
            [reference.destiny_id for reference in references]
        ):
            for evidence in batched(evidence_page.values(), MAX_CONCURRENCY):
                examples = [
                    dspy.Example(
                        evidence=piece_of_evidence,
                        screening_criteria=screening_criteria,
                    ).with_inputs("evidence", "screening_criteria")
                    for piece_of_evidence in evidence
                ]
                predictions: list[ScreeningResult | None] = tracker.fan_out(
                    EvidenceScreener(), examples
                )

                screening_rows: list[ScreeningRow] = []
                for _evidence, prediction in zip(evidence, predictions, strict=True):
                    if prediction is None:
                        logger.warning(
                            "screening failed for id %s", _evidence.destiny_id
                        )
                        continue
                    included += int(prediction.include)
                    screening_rows.append(
                        ScreeningRow(
                            destiny_id=_evidence.destiny_id,
                            include=prediction.include,
                            reasoning=prediction.reasoning,
                            criteria_version=criteria_version or 1,
                        )
                    )

                ctx.set_screening(screening_rows)

        return {
            "screened": total_references,
            "included": included,
            "failed": tracker.failed,
        }
