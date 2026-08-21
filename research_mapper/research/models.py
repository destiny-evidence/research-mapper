from uuid import UUID

from sqlalchemy import UUID as SQL_UUID
from sqlalchemy import Enum, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from research_mapper.db.base import Base
from research_mapper.research.enums import SessionReferenceStage


class SessionReference(Base):
    __tablename__ = "session_references"

    research_session_id: Mapped[UUID] = mapped_column(
        SQL_UUID(as_uuid=True),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    destiny_id: Mapped[UUID] = mapped_column(SQL_UUID(as_uuid=True), nullable=False)
    stage: Mapped[SessionReferenceStage] = mapped_column(
        Enum(
            SessionReferenceStage,
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
            length=32,
        ),
        nullable=False,
        default=SessionReferenceStage.GATHERED,
    )
    provenance: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    screening: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    coordinate: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    mapping: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)

    __table_args__ = (
        UniqueConstraint(research_session_id, destiny_id),
        Index("ix_session_references_stage", research_session_id, stage, "id"),
    )
