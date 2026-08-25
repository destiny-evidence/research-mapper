"""Turning the question into taxonomy filters."""

import builtins
from typing import ClassVar

from pydantic import BaseModel

from research_mapper.engine.context import StepContext
from research_mapper.engine.registry import Step
from research_mapper.engine.views import AskSpec
from research_mapper.models.common import UserQuery
from research_mapper.models.react import Step as LoopStep
from research_mapper.models.taxonomy_search import ClarificationOptions
from research_mapper.modules.taxonomy_search import build_concept_filter_agent
from research_mapper.taxonomy import (
    RepoCommunity,
    build_concept_index,
    get_taxonomy,
)
from research_mapper.workflows.evidence_map import artifacts

UNSURE = "I'm not sure / none of these"


class UnsatisfiableQuery(Exception):
    """The taxonomy cannot express what the user asked for."""


class GenerateConceptFiltersParams(BaseModel):
    """Inputs to generate_concept_filters."""


class GenerateConceptFilters(Step[GenerateConceptFiltersParams, StepContext]):
    """Drive the concept-filter agent, pausing whenever it asks the user something."""

    type: ClassVar[str] = "generate_concept_filters"
    Params: ClassVar[builtins.type[BaseModel]] = GenerateConceptFiltersParams

    def run(self, ctx: StepContext, params: GenerateConceptFiltersParams) -> dict:
        """Run the agent to a set of concept filters, resolved to IRIs."""
        community = RepoCommunity(ctx.research_session.community)
        indexed = build_concept_index(get_taxonomy(community))
        inputs = {
            "user_query": UserQuery(query=ctx.research_session.question),
            "taxonomy_concepts": indexed.concepts,
        }
        agent = build_concept_filter_agent()

        saved = ctx.get_artifact(artifacts.CONCEPT_FILTER_LOOP)
        result = (
            LoopStep.model_validate({**saved.step, "trajectory": saved.trajectory})
            if saved
            else agent.start(**inputs)
        )
        asked = 0
        while isinstance(result, LoopStep):
            if result.tool_name == "mark_unsatisfiable":
                raise UnsatisfiableQuery(result.tool_args["reason"])
            if result.tool_name == "ask_for_clarification":
                ctx.write_artifact(
                    artifacts.CONCEPT_FILTER_LOOP,
                    artifacts.LoopState(
                        step=result.model_dump(mode="json", exclude={"trajectory"}),
                        trajectory=result.trajectory,
                    ),
                )
                answer = ctx.ask(f"clarify:{result.idx}", _spec(result))
                asked += 1
                result = result.with_observation([a["option"] for a in answer])
            result = agent.resume(result, **inputs)

        label_by_ref = {
            concept.local_ref: concept.label for concept in indexed.concepts
        }
        groups = [
            artifacts.ConceptFilter(
                scheme=group.scheme,
                concept_local_refs=group.concept_local_refs,
                reason=group.reason,
                labels=[label_by_ref[ref] for ref in group.concept_local_refs],
                concepts=indexed.resolve(group.concept_local_refs),
            )
            for group in result.filter_groups
        ]
        version = ctx.write_artifact(
            artifacts.CONCEPT_FILTERS,
            artifacts.ConceptFilters(
                community=community, groups=groups, reasoning=result.reasoning
            ),
        )
        return {"filter_groups": len(groups), "questions": asked, "version": version}


def _spec(step: LoopStep) -> AskSpec:
    """The agent's own clarifying question, as a decision."""
    request = ClarificationOptions(**step.tool_args["request"])
    options = [*request.options, UNSURE]
    return AskSpec(
        type="select_many",
        prompt=request.question,
        options=[
            {"id": str(i), "label": option, "value": {"option": option}}
            for i, option in enumerate(options)
        ],
        constraints={"min": 1, "exclusive": [{"option": UNSURE}]},
    )
