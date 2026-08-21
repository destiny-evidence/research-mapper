from enum import StrEnum, auto


class SessionReferenceStage(StrEnum):
    GATHERED = auto()
    INCLUDED = auto()
    EXCLUDED = auto()
    MAPPED = auto()
    FAILED = auto()
