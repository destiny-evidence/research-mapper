from typing import ClassVar, Protocol

from pydantic import BaseModel

from research_mapper.workflow.context import StepContext


class Step(Protocol):
    type: ClassVar[str]
    Params: ClassVar[type[BaseModel]]
    mutates_state: ClassVar[bool] = True

    def run(self, ctx: StepContext, params: BaseModel) -> dict: ...


class GenerateSearchQueries:
    