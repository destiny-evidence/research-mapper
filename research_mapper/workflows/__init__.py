from research_mapper.engine.registry import register


def load() -> None:
    """Register every workflow's steps. Both entry points call this; safe to repeat."""
    from research_mapper.workflows.evidence_map.steps import STEPS

    for step in STEPS:
        register(step)
