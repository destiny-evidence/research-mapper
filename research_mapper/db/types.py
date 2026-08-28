"""Custom database types."""

from typing import Any

from pydantic import BaseModel
from sqlalchemy import Dialect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator


class PydanticJSONB[T: BaseModel](TypeDecorator[T]):
    """A JSONB column that round-trips through a pydantic model."""

    impl = JSONB
    cache_ok = True

    def __init__(self, model: type[T]) -> None:
        super().__init__()
        self.model = model

    def process_bind_param(self, value: T | None, dialect: Dialect) -> Any | None:
        if value is None:
            return None
        return value.model_dump(mode="json")

    def process_result_value(self, value: Any | None, dialect: Dialect) -> T | None:
        if value is None:
            return None
        return self.model.model_validate(value)
