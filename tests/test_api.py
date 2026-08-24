import builtins

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from research_mapper.api.app import app
from research_mapper.api.deps import get_session_factory
from research_mapper.config import init_database
from research_mapper.engine import registry, runner
from research_mapper.engine.context import StepContext
from research_mapper.engine.registry import Step, register
from research_mapper.engine.views import AskSpec

SESSION = {"workflow": "evidence_map", "question": "q", "community": "climate"}
SUGGESTED = "suggested_queries"
CHOSEN = "queries"
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


@pytest.fixture
def client(session_factory, queued):
    """A client over the test database, with one throwaway step registered."""
    before = set(registry.REGISTRY)
    generated = []

    def body(self, ctx, params):
        if ctx.get_artifact(SUGGESTED) is None:
            generated.append(1)
            ctx.put_artifact(SUGGESTED, {"queries": [ONE, TWO]})
        chosen = ctx.ask("select_queries", SPEC)
        ctx.put_artifact(CHOSEN, {"queries": chosen})
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
        runner.run_operation(operation.id, session_factory, StepContext)


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
    question = operation["pending_question"]
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
    assert operation["pending_question"] is None

    detail = client.get(f"/sessions/{session_id}/").json()
    assert detail["head_version_number"] == 1
    assert detail["artifacts"] == {SUGGESTED: 1, CHOSEN: 1}

    artifact = client.get(f"/sessions/{session_id}/artifacts/{CHOSEN}/").json()
    assert artifact == {"type": CHOSEN, "version": 1, "payload": {"queries": [ONE]}}

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
    reply = client.post("/sessions/", json=SESSION | {"workflow": "evidence-map"})
    assert reply.status_code == 400

    created = client.post("/sessions/", json=SESSION)
    assert created.status_code == 201
    assert created.json()["workflow"] == "evidence_map"
