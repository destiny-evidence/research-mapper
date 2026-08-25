"""Generic view models."""

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer


class AskSpec(BaseModel):
    """A question for the user."""

    type: Literal["select_many", "edit_list"]
    prompt: str
    options: list[dict]
    constraints: dict = Field(default_factory=dict)


class Progress(BaseModel):
    """How far an operation has got."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    done: int = 0
    total: int | None = None
    failed: int = 0
    note: str = ""


# jsonb doesn't preserve key order, so for things like trajectories we need to
# define our own structure
Ordered = Annotated[
    dict[str, Any],
    BeforeValidator(lambda value: dict(value) if isinstance(value, list) else value),
    PlainSerializer(lambda value: [[k, v] for k, v in value.items()], return_type=list),
]


@dataclass(frozen=True, slots=True)
class ArtifactSpec[T: BaseModel]:
    """The name and shape of one artifact type."""

    name: str
    model: type[T]
