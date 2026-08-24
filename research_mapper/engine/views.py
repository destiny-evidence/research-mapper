from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AskSpec(BaseModel):
    type: Literal["select_many", "edit_list"]
    prompt: str
    options: list[dict]
    constraints: dict = Field(default_factory=dict)


class Progress(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    done: int = 0
    total: int | None = None
    failed: int = 0
    note: str = ""


@dataclass(frozen=True, slots=True)
class ArtifactSpec[T: BaseModel]:
    name: str
    model: type[T]
