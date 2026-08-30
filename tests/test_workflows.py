from uuid import uuid4

import pytest

from research_mapper import workflows
from research_mapper.engine.context import StepContext


class OtherContext(StepContext):
    """Stand in for a workflow that needs more than the engine's own context."""


# StepContext opens no connection until something reads through it, so these
# need no database.
SESSION_FACTORY = None


def test_a_workflow_gets_the_context_it_declared(monkeypatch):
    """The worker builds whatever the session's workflow asked for, not a fixed class."""
    monkeypatch.setitem(
        workflows.WORKFLOWS,
        "other",
        workflows.Workflow(steps=[], context=OtherContext),
    )

    built = workflows.context("other", uuid4(), SESSION_FACTORY)

    assert isinstance(built, OtherContext)


def test_an_unregistered_workflow_has_no_context():
    """The runner turns this into a failed operation rather than a stuck session."""
    with pytest.raises(LookupError):
        workflows.context("never-shipped", uuid4(), SESSION_FACTORY)
