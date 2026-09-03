"""Turning the question into taxonomy filters."""

import builtins
from typing import ClassVar, Protocol

from pydantic import BaseModel

from research_mapper.engine.context import StepContext
from research_mapper.engine.registry import Step
from research_mapper.engine.views import AskSpec
from research_mapper.models.common import UserQuery
from research_mapper.models.react import Step as LoopStep
from research_mapper.models.taxonomy_search import (
    ClarificationOptions,
    ConceptFilterGroup,
)
from research_mapper.modules.taxonomy_search import (
    NONE_OF_THESE_OPTION,
    SENTINEL_OPTIONS,
    TaxonomyConceptFilterGenerator,
)
from research_mapper.taxonomy import (
    RepoCommunity,
    build_concept_index,
    get_graph,
)
from research_mapper.workflows.evidence_map import artifacts


class ConceptFilterResult(Protocol):
    """What the concept-filter agent puts on its final Prediction."""

    filter_groups: list[ConceptFilterGroup]
    reasoning: str


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
        graph = get_graph(community)
        indexed = build_concept_index(graph)
        generator = TaxonomyConceptFilterGenerator()
        user_query = UserQuery(query=ctx.research_session.question)

        def advance(step: LoopStep | None) -> LoopStep | ConceptFilterResult:
            # can_ask=True: this generator has no self.ui (nothing to block
            # on), but the worker still needs ask_for_clarification available
            # as a tool — it just answers it via ctx.ask() below instead.
            return generator.resume(
                step, user_query=user_query, indexed=indexed, graph=graph, can_ask=True
            )

        saved = ctx.get_artifact(artifacts.CONCEPT_FILTER_LOOP)
        result = (
            LoopStep.model_validate({**saved.step, "trajectory": saved.trajectory})
            if saved
            else advance(None)
        )
        while isinstance(result, LoopStep):
            outcome = generator.classify_step(result)
            if isinstance(outcome, str):
                raise UnsatisfiableQuery(outcome)
            if isinstance(outcome, ClarificationOptions):
                ctx.write_artifact(
                    artifacts.CONCEPT_FILTER_LOOP,
                    artifacts.LoopState(
                        step=result.model_dump(mode="json", exclude={"trajectory"}),
                        trajectory=result.trajectory,
                    ),
                )
                answer = ctx.ask(f"clarify:{result.idx}", _spec(outcome))
                result = result.with_observation([a["option"] for a in answer])
            result = advance(result)

        filters: ConceptFilterResult = result
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
            for group in filters.filter_groups
        ]
        version = ctx.write_artifact(
            artifacts.CONCEPT_FILTERS,
            artifacts.ConceptFilters(
                community=community, groups=groups, reasoning=filters.reasoning
            ),
        )
        return {"filter_groups": len(groups), "version": version}


def _spec(request: ClarificationOptions) -> AskSpec:
    """The agent's own clarifying question, as a decision."""
    options = [*request.options, *SENTINEL_OPTIONS]
    return AskSpec(
        type="select_many",
        prompt=request.question,
        options=[
            {"id": str(i), "label": option, "value": {"option": option}}
            for i, option in enumerate(options)
        ],
        constraints={"min": 1, "exclusive": [{"option": NONE_OF_THESE_OPTION}]},
    )
