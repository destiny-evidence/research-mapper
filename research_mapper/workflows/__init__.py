"""The workflows this deployment can run."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from research_mapper.db.session import SessionFactory
from research_mapper.engine.context import StepContext
from research_mapper.engine.fork import Cut
from research_mapper.engine.registry import Step, register

if TYPE_CHECKING:
    from fastapi import APIRouter

from research_mapper.workflows.evidence_map.context import EvidenceMapContext
from research_mapper.workflows.evidence_map.fork import fork_state as evidence_map_fork
from research_mapper.workflows.evidence_map.steps import STEPS


@dataclass(frozen=True)
class Workflow:
    """What it takes to run one workflow."""

    steps: list[type[Step]]
    context: type[StepContext]
    fork_state: Callable[[Session, Cut], None] | None = None


WORKFLOWS: dict[str, Workflow] = {
    "evidence_map": Workflow(
        steps=STEPS, context=EvidenceMapContext, fork_state=evidence_map_fork
    ),
}


def load() -> None:
    """Register every workflow's steps. Both entry points call this; safe to repeat."""
    for workflow in WORKFLOWS.values():
        for step in workflow.steps:
            register(step)


def context(
    workflow: str, operation_id: UUID, session_factory: SessionFactory
) -> StepContext:
    """Build the context a workflow's steps expect: the runner's ContextFactory."""
    declared = WORKFLOWS.get(workflow)
    if declared is None:
        msg = f"no workflow registered under {workflow!r}"
        raise LookupError(msg)
    return declared.context(operation_id, session_factory)


def fork_state(workflow: str, db: Session, cut: Cut) -> None:
    """Let a workflow copy its own tables into a fork: the engine's StateFactory."""
    declared = WORKFLOWS.get(workflow)
    if declared is not None and declared.fork_state is not None:
        declared.fork_state(db, cut)


def routers() -> list["APIRouter"]:
    """Every workflow's API routes."""
    from research_mapper.workflows.evidence_map import routes

    return [routes.router]


def names() -> list[str]:
    """The workflows a session may declare."""
    return sorted(WORKFLOWS)
