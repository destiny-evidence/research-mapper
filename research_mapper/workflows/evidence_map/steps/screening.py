import builtins
from typing import ClassVar

from pydantic import BaseModel

from research_mapper.engine.context import StepContext
from research_mapper.engine.registry import Step
from research_mapper.engine.views import AskSpec
from research_mapper.models.common import UserQuery
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.pipeline import CriteriaGenerator


class GenerateScreeningCriteriaParams(BaseModel):
    """Inputs to generate_screening_criteria."""

    regenerate: bool = False


class GenerateScreeningCriteria(Step[GenerateScreeningCriteriaParams, StepContext]):
    """Generate a set of inclusion and exclusion screening criteria."""

    type: ClassVar[str] = "generate_screening_criteria"
    Params: ClassVar[builtins.type[BaseModel]] = GenerateScreeningCriteriaParams

    def run(self, ctx: StepContext, params: GenerateScreeningCriteriaParams) -> dict:
        """Suggest screening criteria, then keep the ones the user picks."""

        def generate() -> artifacts.ScreeningCriteria:
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
