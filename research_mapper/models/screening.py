from enum import StrEnum, auto

from pydantic import BaseModel
from dspy.experimental import Noul


class ScreeningCriterionType(StrEnum):
    INCLUSION = auto()
    EXCLUSION = auto()


class ScreeningCriterion(BaseModel):
    criterion_type: ScreeningCriterionType
    description: str

    def __str__(self) -> str:
        return f"{self.criterion_type.value.capitalize()} - {self.description}"


ScreeningDecision = Noul[
    (
        True,
        "Piece of evidence satisfies the screening criteria and should be included.",
    ),
    (
        False,
        "Piece of evidence doesn't satisfy the screening criteria and should be excluded.",
    ),
]
