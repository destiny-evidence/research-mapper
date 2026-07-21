from enum import StrEnum, auto

from pydantic import BaseModel


class ScreeningCriterionType(StrEnum):
    INCLUSION = auto()
    EXCLUSION = auto()


class ScreeningCriterion(BaseModel):
    criterion_type: ScreeningCriterionType
    description: str

    def __str__(self) -> str:
        return f"{self.criterion_type.value.capitalize()} - {self.description}"
