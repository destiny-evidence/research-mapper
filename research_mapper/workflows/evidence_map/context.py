"""Evidence map database context."""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.dialects.postgresql import insert

from research_mapper.workflows.evidence_map.enums import SessionReferenceStage
from research_mapper.workflows.evidence_map.hydrate import DESTINY_LOOKUP_CHUNK_SIZE
from research_mapper.workflows.evidence_map.models import SessionReference
from research_mapper.workflows.evidence_map.views import (
    CoordinateRow,
    ReferenceView,
    RefRow,
    ScreeningRow,
)
from research_mapper.engine.context import StepContext


# A batch is one DESTINY lookup's worth, so a step reads, looks up and decides in step.
BATCH_SIZE = DESTINY_LOOKUP_CHUNK_SIZE


def _by_agent(**fields: object) -> dict:
    """Stamp a decision blob as the agent's, made now."""
    return {**fields, "by": "agent", "at": datetime.now(UTC).isoformat()}


def _view(row: SessionReference) -> ReferenceView:
    return ReferenceView(
        destiny_id=row.destiny_id,
        stage=row.stage,
        screening=row.screening,
        coordinate=row.coordinate,
    )


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

    def _in_session(self) -> Select[tuple[SessionReference]]:
        """Select this session's references."""
        return select(SessionReference).where(
            SessionReference.research_session_id == self.research_session_id
        )

    def _screened_in(self) -> Select[tuple[SessionReference]]:
        """Select every reference screening kept, placed or not."""
        return self._in_session().where(
            SessionReference.stage.in_(
                [SessionReferenceStage.INCLUDED, SessionReferenceStage.MAPPED]
            )
        )

    def _to_map(self, dimensions_version: int) -> Select[tuple[SessionReference]]:
        """Select the references a run against these dimensions has yet to place."""
        return self._screened_in().where(
            SessionReference.mapping["dimensions_version"].astext.is_distinct_from(
                str(dimensions_version)
            )
        )

    def _batches(
        self, statement: Select[tuple[SessionReference]], size: int | None = None
    ) -> Iterator[list[ReferenceView]]:
        """
        The rows `statement` selects, a batch at a time in id order, each read in its
        own short session so a long step holds neither a connection nor every row.

        Paged by id (keyset), not by "the first N still matching": a step moves rows
        out of what it selected as it goes, but one it fails on stays, and must not
        come round again in the same run.
        """
        size = size or BATCH_SIZE
        after: UUID | None = None
        while True:
            page = (
                statement
                if after is None
                else statement.where(SessionReference.id > after)
            )
            with self._sf() as db:
                rows = (
                    db.execute(page.order_by(SessionReference.id).limit(size))
                    .scalars()
                    .all()
                )
                batch = [_view(row) for row in rows]
                after = rows[-1].id if rows else None
            if batch:
                yield batch
            if len(batch) < size:
                return

    def reference_batches(
        self, stage: SessionReferenceStage | None = None, size: int | None = None
    ) -> Iterator[list[ReferenceView]]:
        """This session's references in batches, optionally only those at one stage."""
        statement = self._in_session()
        if stage is not None:
            statement = statement.where(SessionReference.stage == stage)
        return self._batches(statement, size)

    def screened_in_batches(
        self, size: int | None = None
    ) -> Iterator[list[ReferenceView]]:
        """Every reference screening kept, in batches."""
        return self._batches(self._screened_in(), size)

    def batches_to_map(
        self, dimensions_version: int, size: int | None = None
    ) -> Iterator[list[ReferenceView]]:
        """The references a run against these dimensions has yet to place, in batches."""
        return self._batches(self._to_map(dimensions_version), size)

    def _count(self, statement: Select[tuple[SessionReference]]) -> int:
        with self._sf() as db:
            return db.execute(
                select(func.count()).select_from(statement.subquery())
            ).scalar_one()

    def count_references(self, *stages: SessionReferenceStage) -> int:
        """How many of this session's references are at any of these stages."""
        return self._count(self._in_session().where(SessionReference.stage.in_(stages)))

    def count_screened_in(self) -> int:
        """How many references screening kept."""
        return self._count(self._screened_in())

    def count_to_map(self, dimensions_version: int) -> int:
        """How many references a run against these dimensions has yet to place."""
        return self._count(self._to_map(dimensions_version))

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
                            probability=row.probability,
                            threshold=row.threshold,
                            model=row.model,
                            dedicated=row.dedicated,
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
                            probabilities=row.probabilities,
                            model=row.model,
                            dedicated=row.dedicated,
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
