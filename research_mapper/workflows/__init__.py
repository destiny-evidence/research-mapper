from research_mapper.engine.registry import Step, register
from research_mapper.workflows.evidence_map.steps import STEPS

WORKFLOWS: dict[str, list[type[Step]]] = {"evidence_map": STEPS}


def load() -> None:
    """Register every workflow's steps. Both entry points call this; safe to repeat."""
    for steps in WORKFLOWS.values():
        for step in steps:
            register(step)


def names() -> list[str]:
    """The workflows a session may declare."""
    return sorted(WORKFLOWS)
