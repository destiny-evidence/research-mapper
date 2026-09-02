"""API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from research_mapper.engine.enums import DecisionType, OperationStatus
from research_mapper.taxonomy import RepoCommunity
from research_mapper.engine.views import Progress


class CreateSession(BaseModel):
    workflow: str
    question: str
    community: RepoCommunity
    params: dict = {}


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow: str
    question: str
    community: str
    head_version_number: int
    created_at: datetime


class SessionDetail(SessionSummary):
    params: dict
    artifacts: dict[str, int]


class CreateOperation(BaseModel):
    type: str
    params: dict = {}


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    operation_id: UUID
    type: DecisionType
    key: str
    prompt: str
    options: list[dict]
    constraints: dict
    answer: list[dict] | None
    answered_at: datetime | None


class OperationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    research_session_id: UUID
    type: str
    params: dict
    status: OperationStatus
    version_number: int | None
    attempt: int
    progress: Progress
    result: dict | None
    error: dict | None
    pending_questions: list[DecisionOut]
    decisions: list[DecisionOut]


class Respond(BaseModel):
    answers: dict[str, list[dict]] = Field(min_length=1)


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str
    version: int
    payload: dict
