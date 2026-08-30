import builtins

import pytest
from pydantic import BaseModel, ValidationError

from factories import make_operation, make_session, make_user
from research_mapper.engine import queue, registry, runner
from research_mapper.engine.answers import InvalidAnswer
from research_mapper.engine.context import StepContext
from research_mapper.engine.enums import OperationStatus
from research_mapper.engine.models import Decision, Operation, ResearchSession
from research_mapper.engine.registry import Step, register
from research_mapper.engine.views import ArtifactSpec, AskSpec

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


class Draft(BaseModel):
    queries: list[str]


DRAFT = ArtifactSpec("draft", Draft)


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


def plain_context(workflow, operation_id, session_factory) -> StepContext:
    """Stand in for the worker's factory. The engine ships no workflow of its own."""
    return StepContext(operation_id, session_factory)


def run(operation, session_factory):
    runner.run_operation(operation.id, session_factory, plain_context)


def enqueue(operation, session_factory):
    """Put a job on the queue the way the worker would still see it in flight."""
    with session_factory() as db:
        queue.enqueue_in(db, operation.id)
        db.commit()


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
        if ctx.get_artifact(DRAFT) is None:
            generated.append(1)
            ctx.write_artifact(DRAFT, Draft(queries=["a", "b"]))
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

    class Reads(Step[Params, StepContext]):
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

    class Takes(Step[Sized, StepContext]):
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

    class Needs(Step[Sized, StepContext]):
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


def test_a_resume_is_delivered_even_while_the_parking_job_is_still_in_the_queue(
    db, scenario, session_factory, queued
):
    """The job that parked the operation is still in flight; the resume must still land."""
    user, session = scenario
    step("asks", lambda self, ctx, params: {"picked": ctx.ask("pick", SPEC)})
    operation = make_operation(db, session, user, type="asks")
    run(operation, session_factory)
    enqueue(operation, session_factory)
    assert queued() == [str(operation.id)]

    runner.answer_decisions(operation.id, {"pick": [ONE]}, session_factory)

    assert queued() == [str(operation.id)] * 2
    assert reload(db, operation).status == OperationStatus.PENDING


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


def test_a_retry_is_delivered_even_while_the_failed_job_is_still_in_the_queue(
    db, scenario, session_factory, queued
):
    """`_fail` commits from inside the entrypoint, so the job it failed is still in flight."""
    user, session = scenario

    def body(self, ctx, params):
        raise RuntimeError("boom")

    step("boom", body)
    operation = make_operation(db, session, user, type="boom")
    with pytest.raises(RuntimeError):
        run(operation, session_factory)
    enqueue(operation, session_factory)
    assert queued() == [str(operation.id)]

    runner.retry_operation(operation.id, session_factory)

    assert queued() == [str(operation.id)] * 2
    assert reload(db, operation).status == OperationStatus.PENDING


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


def test_a_second_retry_does_not_queue_a_second_job(
    db, scenario, session_factory, queued
):
    """Clicking twice must not run the operation twice; the conditional update is the guard."""
    user, session = scenario
    operation = make_operation(db, session, user, status=OperationStatus.FAILED)

    runner.retry_operation(operation.id, session_factory)
    with pytest.raises(ValueError):
        runner.retry_operation(operation.id, session_factory)

    assert queued() == [str(operation.id)]


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


def test_the_context_is_built_for_the_workflow_the_session_declares(
    db, scenario, session_factory
):
    """The claim carries the workflow name out, so the factory can pick a context."""
    user, session = scenario
    step("counts", lambda self, ctx, params: {"n": 7})
    operation = make_operation(db, session, user, type="counts")
    asked_for = []

    def remembering_context(workflow, operation_id, factory) -> StepContext:
        asked_for.append(workflow)
        return StepContext(operation_id, factory)

    runner.run_operation(operation.id, session_factory, remembering_context)

    assert asked_for == [session.workflow]
    assert reload(db, operation).status == OperationStatus.COMPLETE


def test_an_operation_whose_context_cannot_be_built_fails(
    db, scenario, session_factory
):
    """A workflow this deployment can't build for must not hold the session shut."""
    user, session = scenario
    step("counts", lambda self, ctx, params: {"n": 7})
    unbuildable = make_operation(db, session, user, type="counts")

    def refusing_context(workflow, operation_id, factory) -> StepContext:
        msg = f"no workflow registered under {workflow!r}"
        raise LookupError(msg)

    with pytest.raises(LookupError):
        runner.run_operation(unbuildable.id, session_factory, refusing_context)

    assert reload(db, unbuildable).status == OperationStatus.FAILED
    assert reload(db, unbuildable).error is not None

    # The running slot was released, so the session is still usable.
    later = make_operation(db, session, user, type="counts")
    run(later, session_factory)
    assert reload(db, later).status == OperationStatus.COMPLETE


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


def test_a_redelivered_running_operation_is_taken_over(db, scenario, session_factory):
    """Redelivery only happens once the queue gave up on the previous worker."""
    user, session = scenario
    step("counts", lambda self, ctx, params: {"n": 7})
    zombie = make_operation(
        db, session, user, type="counts", status=OperationStatus.RUNNING
    )

    run(zombie, session_factory)

    assert reload(db, zombie).status == OperationStatus.COMPLETE


def test_a_busy_session_defers_the_next_operation(db, scenario, session_factory):
    """A blocked operation must say so, not fall over on the way in and stay pending."""
    user, session = scenario
    step("counts", lambda self, ctx, params: {"n": 7})
    holder = make_operation(
        db, session, user, type="counts", status=OperationStatus.RUNNING
    )
    waiting = make_operation(db, session, user, type="counts")

    with pytest.raises(runner.SessionBusy):
        run(waiting, session_factory)
    assert reload(db, waiting).status == OperationStatus.PENDING

    # Once the holder is taken over and finishes, the waiting one gets its turn.
    run(holder, session_factory)
    run(waiting, session_factory)
    assert reload(db, waiting).status == OperationStatus.COMPLETE


def test_redelivering_a_finished_operation_does_not_rerun_it(
    db, scenario, session_factory
):
    """The queue delivers at least once; a second delivery must be a no-op."""
    user, session = scenario
    runs = []
    step("counts", lambda self, ctx, params: runs.append(1) or {"n": len(runs)})
    operation = make_operation(db, session, user, type="counts")

    run(operation, session_factory)
    run(operation, session_factory)

    finished = reload(db, operation)
    assert runs == [1]
    assert finished.result == {"n": 1}
    assert finished.version_number == 1
    assert db.get(ResearchSession, session.id).head_version_number == 1


def test_answering_the_last_question_resumes_even_under_a_concurrent_answer(
    db, scenario, session_factory, queued
):
    """Two callers each answering part of the set must not both leave it parked."""
    import threading

    user, session = scenario
    keys = ("first", "second")
    step("asks", lambda self, ctx, params: ctx.ask_all({k: SPEC for k in keys}))
    operation = make_operation(db, session, user, type="asks")
    run(operation, session_factory)
    assert reload(db, operation).status == OperationStatus.AWAITING_INPUT

    # Hold the first caller open between its read and its commit, so the second
    # runs while the first still believes both questions are unanswered.
    reading = threading.Event()
    finish = threading.Event()
    real_validate = runner.validate_answer

    def gated(decision, answer):
        real_validate(decision, answer)
        if not reading.is_set():
            reading.set()
            finish.wait(timeout=10)

    def answer(key):
        runner.answer_decisions(operation.id, {key: [ONE]}, session_factory)

    runner.validate_answer = gated
    try:
        threads = [threading.Thread(target=answer, args=(key,)) for key in keys]
        threads[0].start()
        assert reading.wait(timeout=10)
        threads[1].start()
        threads[1].join(timeout=0.5)
        finish.set()
        for thread in threads:
            thread.join(timeout=10)
    finally:
        runner.validate_answer = real_validate

    db.expire_all()
    assert not db.query(Decision).filter(Decision.answer.is_(None)).count()
    assert reload(db, operation).status == OperationStatus.PENDING
    assert queued() == [str(operation.id)]
