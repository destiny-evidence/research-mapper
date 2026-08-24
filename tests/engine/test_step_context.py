import pytest
from pydantic import BaseModel

from factories import make_operation, make_session, make_user
from research_mapper.engine.context import NeedsInput, StepContext
from research_mapper.engine.enums import DecisionType
from research_mapper.engine.models import Decision, Operation, ResearchSession
from research_mapper.engine.views import ArtifactSpec, AskSpec, Ordered, Progress

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


@pytest.fixture
def operation(db):
    user = make_user(db)
    session = make_session(db, user)
    return make_operation(
        db, session, user, type="enhance_sparse_query", params={"regenerate": True}
    )


@pytest.fixture
def ctx(operation, session_factory):
    return StepContext(operation.id, session_factory)


def answer(db, operation, key, value, type=DecisionType.SELECT_MANY):
    db.add(
        Decision(
            research_session_id=operation.research_session_id,
            operation_id=operation.id,
            type=type,
            key=key,
            prompt="pick",
            answer=value,
        )
    )
    db.commit()


def test_reads_its_operation_and_session(ctx, operation):
    """The session stays readable after the loading session closed."""
    assert ctx.operation_type == "enhance_sparse_query"
    assert ctx.params == {"regenerate": True}
    assert ctx.research_session_id == operation.research_session_id
    assert ctx.research_session.question == "Does X affect Y?"


class Payload(BaseModel):
    n: int


PAYLOAD = ArtifactSpec("payload", Payload)
OTHER = ArtifactSpec("other", Payload)


def test_artifacts_are_versioned_per_type(ctx):
    """A spec carries its model, so a step reads a payload rather than a dict."""
    assert ctx.get_artifact(PAYLOAD) is None
    assert ctx.write_artifact(PAYLOAD, Payload(n=1)) == 1
    assert ctx.write_artifact(PAYLOAD, Payload(n=2)) == 2
    assert ctx.write_artifact(OTHER, Payload(n=1)) == 1

    assert ctx.get_artifact(PAYLOAD) == Payload(n=2)


def test_artifact_versions_are_readable_without_the_payload(ctx):
    """screen_evidence stamps the version of the criteria it screened against."""
    assert ctx.get_artifact_version(PAYLOAD) is None

    ctx.write_artifact(PAYLOAD, Payload(n=1))
    ctx.write_artifact(PAYLOAD, Payload(n=2))
    ctx.write_artifact(OTHER, Payload(n=1))

    assert ctx.get_artifact_version(PAYLOAD) == 2
    assert ctx.get_artifact_version(OTHER) == 1


def test_generating_an_artifact_happens_once_across_restarts(ctx):
    """The checkpoint: a step that blocks on a question doesn't pay for the LM twice."""
    calls = []

    def generate() -> Payload:
        calls.append(1)
        return Payload(n=len(calls))

    assert ctx.get_or_generate_artifact(PAYLOAD, generate) == Payload(n=1)
    assert ctx.get_or_generate_artifact(PAYLOAD, generate) == Payload(n=1)
    assert calls == [1]
    assert ctx.get_artifact_version(PAYLOAD) == 1


def test_regenerating_overwrites_the_checkpoint(ctx):
    def generate() -> Payload:
        return Payload(n=9)

    ctx.write_artifact(PAYLOAD, Payload(n=1))
    assert ctx.get_or_generate_artifact(PAYLOAD, generate, regenerate=True) == Payload(
        n=9
    )
    assert ctx.get_artifact_version(PAYLOAD) == 2


def test_writing_a_model_the_spec_does_not_declare_is_refused(ctx):
    """mypy catches this statically; the guard is for anything reaching it untyped."""
    with pytest.raises(TypeError, match="Payload"):
        ctx.write_artifact(PAYLOAD, AskSpec(type="select_many", prompt="p", options=[]))  # type: ignore[arg-type]


def test_require_names_the_artifact_that_is_missing(ctx):
    with pytest.raises(LookupError, match="payload"):
        ctx.require_artifact(PAYLOAD)


def test_answers_are_scoped_to_this_operation(db, ctx, operation, session_factory):
    """A rerun under a new operation must ask again rather than reuse the old answer."""
    answer(db, operation, "pick", [ONE])
    assert ctx.get_answers(["pick"]) == {"pick": [ONE]}

    session = db.get(ResearchSession, operation.research_session_id)
    later = make_operation(db, session, make_user(db, "other"))
    assert StepContext(later.id, session_factory).get_answers(["pick"]) == {}


def test_ask_blocks_until_answered(db, ctx, operation, session_factory):
    with pytest.raises(NeedsInput):
        ctx.ask("pick", SPEC)
    assert ctx.pending_decisions == {"pick": SPEC}

    answer(db, operation, "pick", [ONE])
    assert StepContext(operation.id, session_factory).ask("pick", SPEC) == [ONE]


def test_ask_all_only_reports_what_is_missing(db, ctx, operation):
    answer(db, operation, "known", [ONE])

    with pytest.raises(NeedsInput):
        ctx.ask_all({"known": SPEC, "unknown": SPEC})
    assert set(ctx.pending_decisions) == {"unknown"}


def test_progress_is_throttled_but_never_drops_the_last_update(db, ctx, operation):
    ctx.progress(done=1, total=3)
    ctx.progress(done=2, total=3)
    assert current_progress(db, operation).done == 1

    ctx.progress(done=3, total=3, note="done")
    assert current_progress(db, operation) == Progress(done=3, total=3, note="done")


def current_progress(db, operation) -> Progress:
    db.expire_all()
    reloaded = db.get(Operation, operation.id)
    assert reloaded is not None
    return reloaded.progress


def test_needs_input_inherits_base_exception():
    """NeedsInput must inherit BaseException as ReAct interrupts Exception propagation"""
    assert issubclass(NeedsInput, BaseException) and not issubclass(
        NeedsInput, Exception
    )


class Loop(BaseModel):
    trajectory: Ordered


LOOP = ArtifactSpec("loop", Loop)


def test_an_ordered_mapping_keeps_its_key_order_through_jsonb(ctx):
    """jsonb sorts object keys; ReAct truncates by insertion order. Hence the array."""
    trajectory = {}
    for i in range(3):
        trajectory |= {
            f"thought_{i}": "t",
            f"tool_name_{i}": "ask",
            f"tool_args_{i}": {},
            f"observation_{i}": ["a"],
        }

    ctx.write_artifact(LOOP, Loop(trajectory=trajectory))
    stored = (
        ctx.read_artifact(LOOP)
        if hasattr(ctx, "read_artifact")
        else ctx.get_artifact(LOOP)
    )

    assert stored is not None
    assert list(stored.trajectory) == list(trajectory)
    assert stored.trajectory == trajectory
