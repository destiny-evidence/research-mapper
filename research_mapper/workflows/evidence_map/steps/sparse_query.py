import builtins
from typing import ClassVar

from pydantic import BaseModel

from research_mapper.models.common import UserQuery
from research_mapper.workflows.evidence_map.pipeline import SparseQueryGenerator
from research_mapper.engine.context import StepContext
from research_mapper.engine.registry import Step
from research_mapper.engine.views import AskSpec


SUGGESTED = "suggested_search_queries"
CHOSEN = "search_queries"


class SparseQueryParams(BaseModel):
    """Inputs to enhance_sparse_query."""

    regenerate: bool = False


class EnhanceSparseQuery(Step[SparseQueryParams]):
    """Suggest Lucene queries for the session question and keep the user's picks."""

    type: ClassVar[str] = "enhance_sparse_query"
    Params: ClassVar[builtins.type[BaseModel]] = SparseQueryParams

    def run(self, ctx: StepContext, params: SparseQueryParams) -> dict:
        """Suggest Lucene queries, then keep the ones the user picks."""
        suggested = None if params.regenerate else ctx.get_artifact(SUGGESTED)
        if suggested is None:
            prediction = SparseQueryGenerator()(
                user_query=UserQuery(query=ctx.research_session.question)
            )
            payload = {
                "queries": [
                    q.model_dump(mode="json") for q in prediction.search_queries
                ]
            }
            ctx.put_artifact(SUGGESTED, payload)
        else:
            payload = suggested.payload

        chosen = ctx.ask(
            "select_queries",
            AskSpec(
                type="select_many",
                prompt="Which of these searches should we run?",
                options=[
                    {"id": str(i), "label": q["query"], "value": q}
                    for i, q in enumerate(payload["queries"])
                ],
                constraints={"min": 1},
            ),
        )
        version = ctx.put_artifact(CHOSEN, {"queries": chosen})
        return {
            "suggested": len(payload["queries"]),
            "selected": len(chosen),
            "version": version,
        }
