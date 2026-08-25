"""The workflows this deployment can run."""

from typing import TYPE_CHECKING

from research_mapper.engine.registry import Step, register

if TYPE_CHECKING:
    from fastapi import APIRouter

from research_mapper.workflows.evidence_map.steps import STEPS

WORKFLOWS: dict[str, list[type[Step]]] = {"evidence_map": STEPS}


def load() -> None:
    """Register every workflow's steps. Both entry points call this; safe to repeat."""
    for steps in WORKFLOWS.values():
        for step in steps:
            register(step)


def routers() -> list["APIRouter"]:
    """Every workflow's API routes."""
    from research_mapper.workflows.evidence_map import routes

    return [routes.router]


def names() -> list[str]:
    """The workflows a session may declare."""
    return sorted(WORKFLOWS)
