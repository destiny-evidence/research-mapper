import builtins

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from research_mapper import workflows
from research_mapper.api.app import app
from research_mapper.api.deps import get_session_factory
from research_mapper.config import init_database
from research_mapper.engine import registry, runner
from research_mapper.engine.registry import Step, register
from research_mapper.engine.views import ArtifactSpec, AskSpec

SESSION = {"workflow": "drafts", "question": "q", "community": "hpv"}

ONE = {"query": "a"}
TWO = {"query": "b"}
SPEC = AskSpec(
    type="select_many",
    prompt="Which searches should we run?",
    options=[
        {"id": "1", "label": "a", "value": ONE},
        {"id": "2", "label": "b", "value": TWO},
    ],
    constraints={"min": 1},
)


class Params(BaseModel):
    regenerate: bool = False


class Queries(BaseModel):
    queries: list[dict]


SUGGESTED = ArtifactSpec("suggested_queries", Queries)
CHOSEN = ArtifactSpec("queries", Queries)


@pytest.fixture
def client(session_factory, queued, stub_workflow):
    """A client over the test database, with one throwaway step registered."""
    before = set(registry.REGISTRY)
    generated = []

    def body(self, ctx, params):
        if ctx.get_artifact(SUGGESTED) is None:
            generated.append(1)
            ctx.write_artifact(SUGGESTED, Queries(queries=[ONE, TWO]))
        chosen = ctx.ask("select_queries", SPEC)
        ctx.write_artifact(CHOSEN, Queries(queries=chosen))
        return {"selected": len(chosen)}

    register(
        builtins.type(
            "Drafts", (Step,), {"type": "drafts", "Params": Params, "run": body}
        )
    )
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as test_client:
        test_client.generated = generated
        yield test_client
    # The app's lifespan disposes db_manager on shutdown, and the session-scoped
    # fixtures share it, so put it back.
    init_database()
    app.dependency_overrides.clear()
    for operation_type in set(registry.REGISTRY) - before:
        del registry.REGISTRY[operation_type]


def work(session_factory) -> None:
    """Stand in for the worker: run whatever is on the queue."""
    from research_mapper.engine.models import Operation
    from research_mapper.engine.enums import OperationStatus

    with session_factory() as db:
        pending = list(
            db.query(Operation).filter_by(status=OperationStatus.PENDING).all()
        )
    for operation in pending:
        runner.run_operation(operation.id, session_factory, workflows.context)


def test_healthz_needs_no_database(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_the_whole_flow_over_http(client, session_factory, queued):
    """The acceptance test, minus killing the container between steps."""
    created = client.post("/sessions", json=SESSION | {"question": "Does X affect Y?"})
    assert created.status_code == 201
    session_id = created.json()["id"]

    accepted = client.post(
        f"/sessions/{session_id}/operations/", json={"type": "drafts"}
    )
    assert accepted.status_code == 202
    operation_id = accepted.json()["id"]
    assert queued() == [operation_id]

    work(session_factory)

    operation = client.get(f"/operations/{operation_id}/").json()
    assert operation["status"] == "awaiting_input"
    assert len(operation["pending_questions"]) == 1
    question = operation["pending_questions"][0]
    assert question["prompt"] == SPEC.prompt
    assert question["options"] == SPEC.options

    open_now = client.get(f"/sessions/{session_id}/decisions/").json()
    assert [row["id"] for row in open_now] == [question["id"]]

    answered = client.post(
        f"/operations/{operation_id}/respond/",
        json={"answers": {question["key"]: [ONE]}},
    )
    assert answered.status_code == 200
    assert answered.json()["status"] == "pending"

    work(session_factory)

    operation = client.get(f"/operations/{operation_id}/").json()
    assert operation["status"] == "complete"
    assert operation["result"] == {"selected": 1}
    assert operation["version_number"] == 1
    assert operation["pending_questions"] == []

    detail = client.get(f"/sessions/{session_id}/").json()
    assert detail["head_version_number"] == 1
    assert detail["artifacts"] == {SUGGESTED.name: 1, CHOSEN.name: 1}

    artifact = client.get(f"/sessions/{session_id}/artifacts/{CHOSEN.name}/").json()
    assert artifact == {
        "type": CHOSEN.name,
        "version": 1,
        "payload": {"queries": [ONE]},
    }

    assert client.generated == [1], "the pre-question work must not run twice"


def test_an_unknown_operation_type_is_a_400(client):
    session_id = client.post("/sessions", json=SESSION).json()["id"]

    reply = client.post(f"/sessions/{session_id}/operations/", json={"type": "nope"})
    assert reply.status_code == 400


def test_a_bad_answer_is_a_422(client, session_factory):
    session_id = client.post("/sessions", json=SESSION).json()["id"]
    operation_id = client.post(
        f"/sessions/{session_id}/operations/", json={"type": "drafts"}
    ).json()["id"]
    work(session_factory)

    reply = client.post(
        f"/operations/{operation_id}/respond/", json={"answer": [{"query": "invented"}]}
    )
    assert reply.status_code == 422
    assert (
        client.get(f"/operations/{operation_id}/").json()["status"] == "awaiting_input"
    )

    reply = client.post(f"/operations/{operation_id}/respond", json={"answer": []})
    assert reply.status_code == 422, "min=1 must be enforced"


def test_missing_things_are_404(client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/sessions/{missing}").status_code == 404
    assert client.get(f"/operations/{missing}").status_code == 404

    session_id = client.post("/sessions/", json=SESSION).json()["id"]
    assert client.get(f"/sessions/{session_id}/artifacts/nothing/").status_code == 404


def test_a_session_must_declare_a_known_workflow(client):
    """The column is only worth having if a typo can't create an unrunnable session."""
    reply = client.post("/sessions/", json=SESSION | {"workflow": "no-such"})
    assert reply.status_code == 400

    created = client.post("/sessions/", json=SESSION)
    assert created.status_code == 201
    assert created.json()["workflow"] == "drafts"


BATCH = {
    key: AskSpec(
        type="edit_list",
        prompt=f"Edit the subtopics of {key}.",
        options=[{"id": "1", "label": key, "value": {"name": key}}],
        constraints={"min": 1, "allow_new": True},
    )
    for key in ("first", "second", "third")
}


@pytest.fixture
def batching_client(session_factory, queued, stub_workflow):
    """A client whose one step asks three questions at once, as ask_all does."""
    before = set(registry.REGISTRY)

    def body(self, ctx, params):
        answers = ctx.ask_all(BATCH)
        return {"answered": sorted(answers)}

    register(
        builtins.type(
            "Batched", (Step,), {"type": "batched", "Params": Params, "run": body}
        )
    )
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as test_client:
        yield test_client
    init_database()
    app.dependency_overrides.clear()
    for operation_type in set(registry.REGISTRY) - before:
        del registry.REGISTRY[operation_type]


def test_an_operation_can_be_parked_on_several_questions(batching_client, session_factory):
    """ask_all opens one decision per question, and all of them must be visible."""
    session_id = batching_client.post("/sessions/", json=SESSION).json()["id"]
    operation_id = batching_client.post(
        f"/sessions/{session_id}/operations/", json={"type": "batched"}
    ).json()["id"]
    work(session_factory)

    operation = batching_client.get(f"/operations/{operation_id}/").json()
    assert operation["status"] == "awaiting_input"
    assert sorted(row["key"] for row in operation["pending_questions"]) == [
        "first",
        "second",
        "third",
    ]

    # Answering a subset leaves the operation parked on the rest, rather than
    # requeueing it with questions still open.
    partial = batching_client.post(
        f"/operations/{operation_id}/respond/",
        json={"answers": {"first": [{"name": "first"}]}},
    )
    assert partial.status_code == 200
    assert partial.json()["status"] == "awaiting_input"
    assert sorted(row["key"] for row in partial.json()["pending_questions"]) == [
        "second",
        "third",
    ]

    rest = batching_client.post(
        f"/operations/{operation_id}/respond/",
        json={
            "answers": {
                "second": [{"name": "second"}],
                "third": [{"name": "third"}],
            }
        },
    )
    assert rest.json()["status"] == "pending"
    assert rest.json()["pending_questions"] == []

    work(session_factory)
    done = batching_client.get(f"/operations/{operation_id}/").json()
    assert done["status"] == "complete"
    assert done["result"] == {"answered": ["first", "second", "third"]}
