import builtins

import pytest
from pydantic import BaseModel, ValidationError

from factories import make_operation, make_session, make_user
from research_mapper.engine import registry, runner
from research_mapper.engine.answers import InvalidAnswer
from research_mapper.engine.context import StepContext
from research_mapper.engine.enums import OperationStatus
from research_mapper.engine.models import Decision, Operation, ResearchSession
from research_mapper.engine.registry import Step, register
from research_mapper.engine.views import AskSpec

ONE = {"query": "a"}
TWO = {"query": "b"}
SPEC = AskSpec(
    type="select_many",
    prompt="pick some",
    options=[
        {"id": "1", "label": "a", "value": ONE},
        {"id": "2", "label": "b", "value": TWO},
    ],
)


class Params(BaseModel):
    pass


@pytest.fixture(autouse=True)
def clean_registry():
    """Drop only what this test registered; imports are cached and never re-run."""
    before = set(registry.REGISTRY)
    yield
    for operation_type in set(registry.REGISTRY) - before:
        del registry.REGISTRY[operation_type]


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

    decision.answer = [ONE]
    db.commit()
    run(operation, session_factory)

    assert reload(db, operation).status == OperationStatus.COMPLETE
    assert reload(db, operation).result == {"picked": [ONE]}
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


def test_create_operation_records_and_queues_it(db, scenario, session_factory, queued):
    user, session = scenario
    step("counts", lambda self, ctx, params: {})

    operation_id = runner.create_operation(
        session.id, user.id, "counts", {}, session_factory
    )

    operation = db.get(Operation, operation_id)
    assert operation is not None
    assert operation.status == OperationStatus.PENDING
    assert queued() == [str(operation_id)]


def test_create_operation_takes_mutates_state_from_the_step(
    db, scenario, session_factory, queued
):
    """The column drives the version bump, so the class value has to reach it."""
    user, session = scenario

    class Reads(Step[Params]):
        type = "reads"
        mutates_state = False
        Params = Params

        def run(self, ctx, params):
            return {}

    register(Reads)
    operation_id = runner.create_operation(
        session.id, user.id, "reads", {}, session_factory
    )

    assert db.get(Operation, operation_id).mutates_state is False


def test_create_operation_persists_validated_params(
    db, scenario, session_factory, queued
):
    user, session = scenario

    class Sized(BaseModel):
        limit: int = 10

    class Takes(Step[Sized]):
        type = "takes"
        Params = Sized

        def run(self, ctx, params):
            return {}

    register(Takes)
    operation_id = runner.create_operation(
        session.id, user.id, "takes", {"limit": "25"}, session_factory
    )

    assert db.get(Operation, operation_id).params == {"limit": 25}


def test_create_operation_rejects_bad_input_before_writing_anything(
    db, scenario, session_factory, queued
):
    """A 422 at the boundary, rather than a red operation the worker discovers."""
    user, session = scenario

    class Sized(BaseModel):
        limit: int

    class Needs(Step[Sized]):
        type = "needs"
        Params = Sized

        def run(self, ctx, params):
            return {}

    register(Needs)

    with pytest.raises(LookupError):
        runner.create_operation(session.id, user.id, "nope", {}, session_factory)
    with pytest.raises(ValidationError):
        runner.create_operation(
            session.id, user.id, "needs", {"limit": "many"}, session_factory
        )

    assert db.query(Operation).count() == 0
    assert queued() == []


def test_answering_the_last_open_decision_resumes_the_operation(
    db, scenario, session_factory, queued
):
    user, session = scenario

    def body(self, ctx, params):
        answers = ctx.ask_all({"a": SPEC, "b": SPEC})
        return {"got": sorted(answers)}

    step("asks", body)
    operation = make_operation(db, session, user, type="asks")
    run(operation, session_factory)
    assert reload(db, operation).status == OperationStatus.AWAITING_INPUT

    assert runner.answer_decisions(operation.id, {"a": [ONE]}, session_factory) is None
    assert reload(db, operation).status == OperationStatus.AWAITING_INPUT
    assert queued() == []

    resumed = runner.answer_decisions(operation.id, {"b": [TWO]}, session_factory)
    assert resumed == operation.id
    assert reload(db, operation).status == OperationStatus.PENDING
    assert queued() == [str(operation.id)]

    db.expire_all()
    assert all(row.answered_at is not None for row in db.query(Decision).all())


def test_an_already_answered_decision_cannot_be_answered_again(
    db, scenario, session_factory, queued
):
    """Re-answering is a client error, not a silent rerun of a finished operation."""
    user, session = scenario
    step("asks", lambda self, ctx, params: {"picked": ctx.ask("pick", SPEC)})
    operation = make_operation(db, session, user, type="asks")
    run(operation, session_factory)

    runner.answer_decisions(operation.id, {"pick": [ONE]}, session_factory)
    run(operation, session_factory)
    assert reload(db, operation).status == OperationStatus.COMPLETE

    with pytest.raises(LookupError):
        runner.answer_decisions(operation.id, {"pick": [TWO]}, session_factory)
    assert reload(db, operation).status == OperationStatus.COMPLETE


def test_retry_requeues_a_failed_operation(db, scenario, session_factory, queued):
    user, session = scenario
    attempts = []

    def body(self, ctx, params):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("transient")
        return {"ok": True}

    step("flaky", body)
    operation = make_operation(db, session, user, type="flaky")
    with pytest.raises(RuntimeError):
        run(operation, session_factory)
    assert reload(db, operation).error is not None

    runner.retry_operation(operation.id, session_factory)
    assert reload(db, operation).status == OperationStatus.PENDING
    assert queued() == [str(operation.id)]

    run(operation, session_factory)
    assert reload(db, operation).status == OperationStatus.COMPLETE
    assert reload(db, operation).error is None, "a retry must clear the stale error"
    assert reload(db, operation).attempt == 1


def test_retry_refuses_an_operation_that_is_not_failed(
    db, scenario, session_factory, queued
):
    """Otherwise a bricked `running` row could be requeued while its step is alive."""
    user, session = scenario
    operation = make_operation(db, session, user, status=OperationStatus.RUNNING)

    with pytest.raises(ValueError):
        runner.retry_operation(operation.id, session_factory)
    assert queued() == []


def test_an_unknown_operation_type_fails_the_operation(db, scenario, session_factory):
    """Registry lookup lives inside the try, so a renamed step can't brick a session."""
    user, session = scenario
    operation = make_operation(db, session, user, type="was-renamed")

    with pytest.raises(LookupError):
        run(operation, session_factory)

    assert reload(db, operation).status == OperationStatus.FAILED


def test_an_invalid_answer_is_rejected_without_touching_the_operation(
    db, scenario, session_factory, queued
):
    user, session = scenario
    step("asks", lambda self, ctx, params: {"picked": ctx.ask("pick", SPEC)})
    operation = make_operation(db, session, user, type="asks")
    run(operation, session_factory)
    decision = db.query(Decision).one()

    with pytest.raises(InvalidAnswer):
        runner.answer_decisions(
            operation.id, {"pick": [{"query": "invented"}]}, session_factory
        )

    db.expire_all()
    assert db.get(Decision, decision.id).answer is None
    assert reload(db, operation).status == OperationStatus.AWAITING_INPUT
    assert queued() == []
