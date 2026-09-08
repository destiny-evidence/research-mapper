"""Choosing which kind of map to build."""

import builtins
from enum import StrEnum, auto
from typing import ClassVar

from pydantic import BaseModel

from research_mapper.engine.context import StepContext
from research_mapper.engine.registry import Step
from research_mapper.engine.views import AskSpec


class MapStyle(StrEnum):
    SUGGESTED = auto()
    TAXONOMY = auto()


STYLES = [
    {
        "id": MapStyle.SUGGESTED,
        "label": "Let it suggest dimensions from your question",
        "detail": (
            "The agent proposes three novel axes. You can edit or update them, "
            "then it places each reference on the map."
        ),
        "value": {"style": MapStyle.SUGGESTED},
    },
    {
        "id": MapStyle.TAXONOMY,
        "label": "Use the taxonomy's own schemes",
        "detail": (
            "The agent selects axes from the taxonomy. References are placed on "
            "the map according to their existing coded values."
        ),
        "value": {"style": MapStyle.TAXONOMY},
    },
]


class ChooseMapStyleParams(BaseModel):
    """Inputs to choose_map_style."""


class ChooseMapStyle(Step[ChooseMapStyleParams, StepContext]):
    """Ask which of the two maps to build, so the answer is a decision to fork at."""

    type: ClassVar[str] = "choose_map_style"
    # It settles a question and writes nothing else, so it is not a checkpoint.
    mutates_state: ClassVar[bool] = False
    Params: ClassVar[builtins.type[BaseModel]] = ChooseMapStyleParams

    def run(self, ctx: StepContext, params: ChooseMapStyleParams) -> dict:
        """Record which map the user wants."""
        chosen = ctx.ask(
            "map_style",
            AskSpec(
                type="select_one",
                prompt="How should the map be built?",
                options=STYLES,
                constraints={"min": 1, "max": 1},
            ),
        )
        return {"style": MapStyle(chosen[0]["style"])}
