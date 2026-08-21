from datetime import datetime
from uuid import UUID

from sqlalchemy import UUID as SQL_UUID
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from research_mapper.db.base import Base
from research_mapper.db.types import PydanticJSONB
from research_mapper.engine.enums import DecisionType, OperationStatus
from research_mapper.engine.views import Progress


class User(Base):
    __tablename__ = "users"

    issuer: Mapped[str] = mapped_column(nullable=False)
    subject: Mapped[str] = mapped_column(nullable=False)

    __table_args__ = (UniqueConstraint(issuer, subject),)


class ResearchSession(Base):
    __tablename__ = "research_sessions"

    user_id: Mapped[UUID] = mapped_column(
        SQL_UUID(as_uuid=True), ForeignKey(User.id), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(String, nullable=False)
    community: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    head_version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    workflow_version: Mapped[str] = mapped_column(String, nullable=False, default="v1")


class Operation(Base):
    __tablename__ = "operations"

    research_session_id: Mapped[UUID] = mapped_column(
        SQL_UUID(as_uuid=True),
        ForeignKey(ResearchSession.id, ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[OperationStatus] = mapped_column(
        Enum(
            OperationStatus,
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
            length=32,
        ),
        nullable=False,
        default=OperationStatus.PENDING,
    )
    mutates_state: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version_number: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    error: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    progress: Mapped[Progress] = mapped_column(
        PydanticJSONB(Progress), nullable=False, default=Progress()
    )
    created_by_id: Mapped[UUID] = mapped_column(
        SQL_UUID(as_uuid=True), ForeignKey(User.id), nullable=False
    )

    research_session: Mapped[ResearchSession] = relationship(lazy="raise_on_sql")

    __table_args__ = (
        Index("ix_operations_session_created", research_session_id, "id"),
        Index(
            "uq_operations_one_running_per_session",
            research_session_id,
            unique=True,
            postgresql_where=status == OperationStatus.RUNNING,
        ),
        UniqueConstraint(research_session_id, version_number),
    )


class Decision(Base):
    __tablename__ = "decisions"

    research_session_id: Mapped[UUID] = mapped_column(
        SQL_UUID(as_uuid=True),
        ForeignKey(ResearchSession.id, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation_id: Mapped[UUID] = mapped_column(
        SQL_UUID(as_uuid=True),
        ForeignKey(Operation.id, ondelete="RESTRICT"),
        nullable=False,
    )
    type: Mapped[DecisionType] = mapped_column(
        Enum(
            DecisionType,
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
            length=32,
        ),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String, nullable=False)
    prompt: Mapped[str] = mapped_column(String, nullable=False)
    options: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    constraints: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    answer: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    __table_args__ = (
        Index(
            "ix_pending_decisions",
            research_session_id,
            postgresql_where=answer.is_(None),
        ),
        UniqueConstraint(operation_id, key),
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    research_session_id: Mapped[UUID] = mapped_column(
        SQL_UUID(as_uuid=True),
        ForeignKey(ResearchSession.id, ondelete="CASCADE"),
        nullable=False,
    )
    operation_id: Mapped[UUID] = mapped_column(
        SQL_UUID(as_uuid=True),
        ForeignKey(Operation.id, ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (UniqueConstraint(research_session_id, type, version),)
