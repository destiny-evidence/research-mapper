import builtins
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel

from research_mapper.engine.context import StepContext

STEP_T = builtins.type["Step[Any]"]
REGISTRY: dict[str, STEP_T] = {}


class Step[P: BaseModel](ABC):
    """One unit of durable work, run by the worker against a StepContext."""

    type: ClassVar[str]
    mutates_state: ClassVar[bool] = True
    Params: ClassVar[builtins.type[BaseModel]]

    @abstractmethod
    def run(self, ctx: StepContext, params: P) -> dict: ...


def register(step: STEP_T) -> STEP_T:
    """Make a step runnable by its operation type."""
    operation_type = getattr(step, "type", None)
    if not isinstance(operation_type, str) or not operation_type:
        msg = f"{step.__name__} needs a non-empty str `type`"
        raise TypeError(msg)
    registered = REGISTRY.get(operation_type)
    if registered is step:
        return step
    if registered is not None:
        msg = f"operation type {operation_type!r} is already registered"
        raise TypeError(msg)
    REGISTRY[operation_type] = step
    return step


def get(operation_type: str) -> STEP_T:
    """Return the step registered for an operation type."""
    step = REGISTRY.get(operation_type)
    if step is None:
        msg = f"no step registered for operation type {operation_type!r}"
        raise LookupError(msg)
    return step


def known_types() -> list[str]:
    """Return every registered operation type."""
    return sorted(REGISTRY)
