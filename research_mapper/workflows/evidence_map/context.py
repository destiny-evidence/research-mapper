"""Evidence map database context."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.dialects.postgresql import insert

from research_mapper.workflows.evidence_map.enums import SessionReferenceStage
from research_mapper.workflows.evidence_map.models import SessionReference
from research_mapper.workflows.evidence_map.views import (
    CoordinateRow,
    ReferenceView,
    RefRow,
    ScreeningRow,
)
from research_mapper.engine.context import StepContext


def _by_agent(**fields: object) -> dict:
    """Stamp a decision blob as the agent's, made now."""
    return {**fields, "by": "agent", "at": datetime.now(UTC).isoformat()}


class EvidenceMapContext(StepContext):
    """A step context with this workflow's references."""

    def _update(self, destiny_id: UUID, **values: object):
        """Build an update of one of this session's references."""
        return (
            update(SessionReference)
            .where(SessionReference.research_session_id == self.research_session_id)
            .where(SessionReference.destiny_id == destiny_id)
            .values(**values)
        )

    def record_references(self, rows: list[RefRow]) -> None:
        """Add references to this session, appending provenance to any already there."""
        with self._sf() as db:
            for row in rows:
                statement = insert(SessionReference).values(
                    research_session_id=self.research_session_id,
                    destiny_id=row.destiny_id,
                    stage=SessionReferenceStage.GATHERED,
                    provenance=[row.provenance],
                )
                db.execute(
                    statement.on_conflict_do_update(
                        index_elements=["research_session_id", "destiny_id"],
                        set_={
                            "provenance": SessionReference.provenance
                            + statement.excluded.provenance
                        },
                    )
                )
            db.commit()

    def references(
        self, stage: SessionReferenceStage | None = None
    ) -> list[ReferenceView]:
        """Return this session's references, optionally only those at one stage."""
        statement = select(
            SessionReference.destiny_id,
            SessionReference.stage,
            SessionReference.screening,
            SessionReference.coordinate,
        ).where(SessionReference.research_session_id == self.research_session_id)
        if stage is not None:
            statement = statement.where(SessionReference.stage == stage)
        with self._sf() as db:
            rows = db.execute(statement).all()
        return [
            ReferenceView(
                destiny_id=row.destiny_id,
                stage=row.stage,
                screening=row.screening,
                coordinate=row.coordinate,
            )
            for row in rows
        ]

    def _screened_in(self) -> Select[tuple[SessionReference]]:
        """Select every reference screening kept, placed or not."""
        return (
            select(SessionReference)
            .where(SessionReference.research_session_id == self.research_session_id)
            .where(
                SessionReference.stage.in_(
                    [SessionReferenceStage.INCLUDED, SessionReferenceStage.MAPPED]
                )
            )
        )

    def _views(self, statement: Select[tuple[SessionReference]]) -> list[ReferenceView]:
        with self._sf() as db:
            rows = db.execute(statement.order_by(SessionReference.id)).scalars().all()
        return [
            ReferenceView(
                destiny_id=row.destiny_id,
                stage=row.stage,
                screening=row.screening,
                coordinate=row.coordinate,
            )
            for row in rows
        ]

    def screened_in(self) -> list[ReferenceView]:
        """Every reference screening kept."""
        return self._views(self._screened_in())

    def references_to_map(self, dimensions_version: int) -> list[ReferenceView]:
        """References a run against these dimensions has yet to place."""
        return self._views(
            self._screened_in().where(
                SessionReference.mapping["dimensions_version"].astext.is_distinct_from(
                    str(dimensions_version)
                )
            )
        )

    def count_mapped_at(self, dimensions_version: int) -> int:
        """How many references are already placed against these dimensions."""
        statement = (
            select(func.count())
            .select_from(SessionReference)
            .where(SessionReference.research_session_id == self.research_session_id)
            .where(SessionReference.stage == SessionReferenceStage.MAPPED)
            .where(
                SessionReference.mapping["dimensions_version"].astext
                == str(dimensions_version)
            )
        )
        with self._sf() as db:
            return db.execute(statement).scalar_one()

    def set_screening(self, rows: list[ScreeningRow]) -> None:
        """Record screening verdicts and move each reference in or out."""
        with self._sf() as db:
            for row in rows:
                db.execute(
                    self._update(
                        row.destiny_id,
                        stage=SessionReferenceStage.INCLUDED
                        if row.include
                        else SessionReferenceStage.EXCLUDED,
                        screening=_by_agent(
                            include=row.include,
                            reasoning=row.reasoning,
                            criteria_version=row.criteria_version,
                        ),
                    )
                )
            db.commit()

    def set_coordinates(self, rows: list[CoordinateRow]) -> None:
        """Record map coordinates and mark each reference mapped."""
        with self._sf() as db:
            for row in rows:
                db.execute(
                    self._update(
                        row.destiny_id,
                        stage=SessionReferenceStage.MAPPED,
                        coordinate=row.coordinate,
                        mapping=_by_agent(
                            reasoning=row.reasoning,
                            dimensions_version=row.dimensions_version,
                        ),
                    )
                )
            db.commit()

    def mark_failed(self, destiny_ids: list[UUID]) -> None:
        """Mark references the pipeline could not process."""
        with self._sf() as db:
            for destiny_id in destiny_ids:
                db.execute(self._update(destiny_id, stage=SessionReferenceStage.FAILED))
            db.commit()
