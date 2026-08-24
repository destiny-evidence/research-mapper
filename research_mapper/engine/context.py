import time
from collections.abc import Collection
from functools import cached_property
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from research_mapper.db.session import SessionFactory
from research_mapper.engine.views import ArtifactView, AskSpec, Progress
from research_mapper.engine.models import (
    Artifact,
    CurrentArtifact,
    Decision,
    Operation,
    ResearchSession,
)

PROGRESS_MIN_INTERVAL_SECONDS = 1.0


class NeedsInput(BaseException):
    """Raised out of a step when a human decision is needed to continue."""


class StepContext:
    def __init__(
        self,
        operation_id: UUID,
        session_factory: SessionFactory,
    ) -> None:
        self.operation_id = operation_id
        self._sf = session_factory
        self._pending: dict[str, AskSpec] = {}
        self._last_progress = 0.0

    @property
    def pending_decisions(self) -> dict[str, AskSpec]:
        """Decisions this step asked for and did not find an answer to."""
        return dict(self._pending)

    @cached_property
    def _operation(self) -> Operation:
        """The operation being run, loaded once with its research session."""
        with self._sf() as db:
            return db.execute(
                select(Operation)
                .options(joinedload(Operation.research_session))
                .where(Operation.id == self.operation_id)
            ).scalar_one()

    @property
    def research_session(self) -> ResearchSession:
        """The research session this operation belongs to."""
        return self._operation.research_session

    @property
    def research_session_id(self) -> UUID:
        """The id of the research session this operation belongs to."""
        return self.research_session.id

    @property
    def operation_type(self) -> str:
        """The registered type of the operation being run."""
        return self._operation.type

    @property
    def params(self) -> dict:
        """The parameters this operation was created with."""
        return self._operation.params

    def _current(self, db: Session, artifact_type: str) -> Artifact | None:
        """The current version of an artifact type in this session, if any."""
        return db.execute(
            select(CurrentArtifact)
            .where(CurrentArtifact.research_session_id == self.research_session_id)
            .where(CurrentArtifact.type == artifact_type)
        ).scalar_one_or_none()

    def get_artifact(self, artifact_type: str) -> ArtifactView | None:
        """Return the current artifact of a type, or None if there is none yet."""
        with self._sf() as db:
            artifact = self._current(db, artifact_type)
            if artifact is None:
                return None
            return ArtifactView(version=artifact.version, payload=artifact.payload)

    def put_artifact(self, artifact_type: str, payload: dict) -> int:
        """Write the next version of an artifact and return its version number."""
        with self._sf() as db:
            current = self._current(db, artifact_type)
            version = current.version + 1 if current else 1
            db.add(
                Artifact(
                    research_session_id=self.research_session_id,
                    operation_id=self.operation_id,
                    type=artifact_type,
                    version=version,
                    payload=payload,
                )
            )
            db.commit()
            return version

    def get_answers(self, keys: Collection[str]) -> dict[str, list[dict]]:
        """Return the answers already given for these decision keys."""
        with self._sf() as db:
            rows = db.execute(
                select(Decision.key, Decision.answer)
                .where(Decision.operation_id == self.operation_id)
                .where(Decision.key.in_(keys))
            ).all()
        return {row.key: row.answer for row in rows if row.answer is not None}

    def ask(self, key: str, spec: AskSpec) -> list[dict]:
        """Return the answer to one decision, or raise NeedsInput."""
        return self.ask_all({key: spec})[key]

    def ask_all(self, specs: dict[str, AskSpec]) -> dict[str, list[dict]]:
        """Return answers to every decision, or raise NeedsInput for the missing ones."""
        answered = self.get_answers(specs.keys())
        missing = specs.keys() - answered.keys()
        if missing:
            self._pending.update({key: specs[key] for key in missing})
            raise NeedsInput
        return answered

    def progress(
        self,
        done: int,
        total: int | None = None,
        failed: int = 0,
        note: str = "",
    ) -> None:
        """Record how far this operation has got, at most once per interval."""
        now = time.monotonic()
        final = total is not None and done >= total
        if not final and now - self._last_progress < PROGRESS_MIN_INTERVAL_SECONDS:
            return
        self._last_progress = now
        with self._sf() as db:
            db.execute(
                update(Operation)
                .where(Operation.id == self.operation_id)
                .values(
                    progress=Progress(done=done, total=total, failed=failed, note=note)
                )
            )
            db.commit()
