import builtins
from typing import ClassVar

from pydantic import BaseModel

from research_mapper.engine.context import StepContext
from research_mapper.engine.registry import Step
from research_mapper.engine.views import AskSpec
from research_mapper.models.common import UserQuery
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.pipeline import SparseQueryGenerator


class SparseQueryParams(BaseModel):
    """Inputs to enhance_sparse_query."""

    regenerate: bool = False


class EnhanceSparseQuery(Step[SparseQueryParams, StepContext]):
    """Suggest Lucene queries for the session question and keep the user's picks."""

    type: ClassVar[str] = "enhance_sparse_query"
    Params: ClassVar[builtins.type[BaseModel]] = SparseQueryParams

    def run(self, ctx: StepContext, params: SparseQueryParams) -> dict:
        """Suggest Lucene queries, then keep the ones the user picks."""

        def generate() -> artifacts.SearchQueries:
            prediction = SparseQueryGenerator()(
                user_query=UserQuery(query=ctx.research_session.question)
            )
            return artifacts.SearchQueries(
                queries=prediction.search_queries, reasoning=prediction.reasoning
            )

        suggested = ctx.get_or_generate_artifact(
            artifacts.SUGGESTED_SEARCH_QUERIES, generate, params.regenerate
        )

        chosen = ctx.ask(
            "select_queries",
            AskSpec(
                type="select_many",
                prompt="Which of these searches should we run?",
                options=[
                    {
                        "id": str(i),
                        "label": query.query,
                        "value": query.model_dump(mode="json"),
                    }
                    for i, query in enumerate(suggested.queries)
                ],
                constraints={"min": 1},
            ),
        )

        version = ctx.write_artifact(
            artifacts.SEARCH_QUERIES,
            artifacts.SearchQueries.model_validate(
                {"queries": chosen, "reasoning": suggested.reasoning}
            ),
        )
        return {
            "suggested": len(suggested.queries),
            "selected": len(chosen),
            "version": version,
        }
