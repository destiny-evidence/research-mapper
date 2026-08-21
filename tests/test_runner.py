import builtins

import pytest
from pydantic import BaseModel

from factories import make_operation, make_session, make_user
from research_mapper.engine import registry, runner
from research_mapper.engine.context import StepContext
from research_mapper.engine.enums import OperationStatus
from research_mapper.engine.models import Decision, Operation, ResearchSession
from research_mapper.engine.registry import Step, register
from research_mapper.engine.views import AskSpec

SPEC = AskSpec(type="select_many", prompt="pick some", options=[{"id": "1"}])


class Params(BaseModel):
    pass


@pytest.fixture(autouse=True)
def clean_registry():
    original = dict(registry.REGISTRY)
    yield
    registry.REGISTRY.clear()
    registry.REGISTRY.update(original)


@pytest.fixture
def scenario(db):
    user = make_user(db)
    return user, make_session(db, user)


def step(name, body):
    """Register a throwaway step so the runner has something to run."""
    return register(
        builtins.type(
            name.title(), (Step,), {"type": name, "Params": Params, "run": body}
        )
    )


def run(operation, session_factory):
    runner.run_operation(operation.id, session_factory, StepContext)


def reload(db, operation) -> Operation:
    db.expire_all()
    reloaded = db.get(Operation, operation.id)
    assert reloaded is not None
    return reloaded


def test_a_completed_operation_takes_the_next_version(db, scenario, session_factory):
    user, session = scenario
    step("counts", lambda self, ctx, params: {"n": 7})
    operation = make_operation(db, session, user, type="counts")

    run(operation, session_factory)

    assert reload(db, operation).status == OperationStatus.COMPLETE
    assert reload(db, operation).result == {"n": 7}
    assert reload(db, operation).version_number == 1
    assert db.get(ResearchSession, session.id).head_version_number == 1


def test_an_operation_that_mutates_nothing_leaves_the_version_alone(
    db, scenario, session_factory
):
    user, session = scenario
    step("reads", lambda self, ctx, params: {})
    operation = make_operation(db, session, user, type="reads", mutates_state=False)

    run(operation, session_factory)

    assert reload(db, operation).status == OperationStatus.COMPLETE
    assert reload(db, operation).version_number is None
    assert db.get(ResearchSession, session.id).head_version_number == 0


def test_an_operation_parks_on_a_question_and_resumes_from_its_artifact(
    db, scenario, session_factory
):
    """The point of ask-and-restart: the work before the question happens once."""
    user, session = scenario
    generated = []

    def body(self, ctx, params):
        if ctx.get_artifact("draft") is None:
            generated.append(1)
            ctx.put_artifact("draft", {"queries": ["a", "b"]})
        picked = ctx.ask("pick", SPEC)
        return {"picked": picked}

    step("drafts", body)
    operation = make_operation(db, session, user, type="drafts")

    run(operation, session_factory)

    assert reload(db, operation).status == OperationStatus.AWAITING_INPUT
    decision = db.query(Decision).one()
    assert (decision.key, decision.prompt) == ("pick", SPEC.prompt)
    assert decision.options == SPEC.options

    decision.answer = ["a"]
    db.commit()
    run(operation, session_factory)

    assert reload(db, operation).status == OperationStatus.COMPLETE
    assert reload(db, operation).result == {"picked": ["a"]}
    assert generated == [1], "the pre-question work should not have run twice"
    assert db.query(Decision).count() == 1


def test_a_failing_operation_records_the_attempt_and_reraises(
    db, scenario, session_factory
):
    user, session = scenario

    def body(self, ctx, params):
        raise RuntimeError("boom")

    step("breaks", body)
    operation = make_operation(db, session, user, type="breaks")

    with pytest.raises(RuntimeError):
        run(operation, session_factory)

    assert reload(db, operation).status == OperationStatus.FAILED
    assert reload(db, operation).attempt == 1
    assert reload(db, operation).error is not None
