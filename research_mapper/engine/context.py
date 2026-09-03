"""Generic database context."""

import time
from collections.abc import Callable, Collection
from functools import cached_property
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from research_mapper.db.session import SessionFactory
from research_mapper.engine.views import ArtifactSpec, AskSpec, Progress
from research_mapper.engine.models import (
    Artifact,
    CurrentArtifact,
    Decision,
    Operation,
    ResearchSession,
)

PROGRESS_MIN_INTERVAL_SECONDS = 1.0


class NeedsInput(BaseException):
    """Raised out of a step when a human decision is needed to continue.

    Not an Exception, so a step catching its own errors cannot swallow a pause.
    """


class StepContext:
    """What a step can read and write while it runs."""

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

    def get_artifact[T: BaseModel](self, artifact: ArtifactSpec[T]) -> T | None:
        """The current artifact."""
        with self._sf() as db:
            current = self._current(db, artifact.name)
            if current is None:
                return None
            return artifact.model.model_validate(current.payload)

    def get_artifact_version[T: BaseModel](
        self, artifact: ArtifactSpec[T]
    ) -> int | None:
        """The current version of an artifact."""
        with self._sf() as db:
            current = self._current(db, artifact.name)
            if current is None:
                return None
            return current.version

    def get_or_generate_artifact[T: BaseModel](
        self,
        artifact: ArtifactSpec[T],
        generate: Callable[[int], T],
        regenerate: bool = False,
    ) -> T:
        """The current artifact, generating and storing it if there isn't one.

        Used to checkpoint steps that require user input after agentic work. An
        operation generates at most once however often it is resumed, so what the
        user answered against stays the current version. `generate` is handed the
        version it supersedes, so a regenerated suggestion can be made to differ.
        """
        with self._sf() as db:
            current = self._current(db, artifact.name)
            payload = None if current is None else current.payload
            superseded = 0 if current is None else current.version
            mine = current is not None and current.operation_id == self.operation_id
        if payload is not None and (mine or not regenerate):
            return artifact.model.model_validate(payload)
        generated = generate(superseded)
        self.write_artifact(artifact, generated)
        return generated

    def require_artifact[T: BaseModel](self, artifact: ArtifactSpec[T]) -> T:
        """The current artifact, raising LookupError if missing."""
        payload = self.get_artifact(artifact)
        if payload is None:
            msg = f"{artifact.name} has not been produced for this session yet"
            raise LookupError(msg)
        return payload

    def write_artifact[T: BaseModel](
        self, artifact: ArtifactSpec[T], payload: T
    ) -> int:
        """Write the next version of an artifact and return its version number."""
        if not isinstance(payload, artifact.model):
            msg = f"{artifact.name} holds {artifact.model.__name__}, not {type(payload).__name__}"
            raise TypeError(msg)
        with self._sf() as db:
            current = self._current(db, artifact.name)
            version = current.version + 1 if current else 1
            db.add(
                Artifact(
                    research_session_id=self.research_session_id,
                    operation_id=self.operation_id,
                    type=artifact.name,
                    version=version,
                    payload=payload.model_dump(mode="json"),
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
