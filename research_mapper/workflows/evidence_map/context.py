from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
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
        statement = select(SessionReference.destiny_id, SessionReference.stage).where(
            SessionReference.research_session_id == self.research_session_id
        )
        if stage is not None:
            statement = statement.where(SessionReference.stage == stage)
        with self._sf() as db:
            rows = db.execute(statement).all()
        return [
            ReferenceView(destiny_id=row.destiny_id, stage=row.stage) for row in rows
        ]

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
