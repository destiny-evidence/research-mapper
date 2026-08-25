"""The workflows this deployment can run."""

from typing import TYPE_CHECKING

from research_mapper.engine.registry import Step, register

if TYPE_CHECKING:
    from fastapi import APIRouter

WORKFLOWS: dict[str, list[type[Step]]] = {}


def load() -> None:
    """Register every workflow's steps. Both entry points call this; safe to repeat."""
    for steps in WORKFLOWS.values():
        for step in steps:
            register(step)


def routers() -> list["APIRouter"]:
    """Every workflow's API routes."""
    return []


def names() -> list[str]:
    """The workflows a session may declare."""
    return sorted(WORKFLOWS)
