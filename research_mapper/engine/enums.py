"""Generic enums."""

from enum import StrEnum, auto


class OperationStatus(StrEnum):
    PENDING = auto()
    RUNNING = auto()
    AWAITING_INPUT = auto()
    COMPLETE = auto()
    FAILED = auto()
    SUPERSEDED = auto()


class DecisionType(StrEnum):
    SELECT_MANY = auto()
    SELECT_ONE = auto()
    EDIT_LIST = auto()
    TEXT = auto()
