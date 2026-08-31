import uuid

import pytest
from fastapi.testclient import TestClient

from factories import make_operation, make_reference, make_session, make_user
from research_mapper.api.app import app
from research_mapper.config import init_database
from research_mapper.engine.models import Artifact
from research_mapper.models.common import Evidence
from research_mapper.workflows.evidence_map import routes
from research_mapper.workflows.evidence_map.enums import SessionReferenceStage
from research_mapper.workflows.evidence_map.artifacts import ArtifactType

ONE = uuid.UUID("11111111-1111-4111-8111-111111111111")
TWO = uuid.UUID("22222222-2222-4222-8222-222222222222")

DIMENSIONS = [
    {
        "name": "Setting",
        "description": "where",
        "subtopics": [{"name": "Urban", "description": "u"}],
    },
    {
        "name": "Outcome",
        "description": "what",
        "subtopics": [{"name": "Mortality", "description": "m"}],
    },
    {
        "name": "Design",
        "description": "how",
        "subtopics": [{"name": "Cohort", "description": "c"}],
    },
]


@pytest.fixture
def client(session_factory):
    with TestClient(app) as test_client:
        yield test_client
    init_database()
    app.dependency_overrides.clear()


@pytest.fixture
def session(db):
    user = make_user(db)
    return make_session(db, user)


def put_dimensions(db, session, dimensions=DIMENSIONS) -> None:
    user = make_user(db, "author")
    operation = make_operation(db, session, user)
    db.add(
        Artifact(
            research_session_id=session.id,
            operation_id=operation.id,
            type=ArtifactType.DIMENSIONS,
            version=1,
            payload={"dimensions": dimensions},
        )
    )
    db.commit()


def test_a_session_with_no_map_yet_is_a_404(client, session):
    assert client.get(f"/sessions/{session.id}/map/").status_code == 404


def test_the_map_joins_the_dimensions_artifact_to_the_reference_rows(
    client, db, session, monkeypatch
):
    put_dimensions(db, session)
    make_reference(
        db,
        session,
        ONE,
        stage=SessionReferenceStage.MAPPED,
        coordinate={
            "Setting": ["Urban"],
            "Outcome": ["Mortality"],
            "Design": ["Cohort"],
        },
    )
    make_reference(db, session, TWO, stage=SessionReferenceStage.EXCLUDED)
    monkeypatch.setattr(
        routes,
        "get_evidence",
        lambda ids: [{ONE: Evidence(destiny_id=ONE, title="A")}],
    )

    body = client.get(f"/sessions/{session.id}/map/").json()

    assert [d["name"] for d in body["dimensions"]] == ["Setting", "Outcome", "Design"]
    assert len(body["mapped_evidence"]) == 1, "only mapped references are cells"
    cell = body["mapped_evidence"][0]
    assert cell["evidence"]["title"] == "A"
    assert cell["coordinate"] == {
        "Setting": ["Urban"],
        "Outcome": ["Mortality"],
        "Design": ["Cohort"],
    }


def test_a_reference_destiny_no_longer_returns_is_dropped(
    client, db, session, monkeypatch
):
    put_dimensions(db, session)
    for destiny_id in (ONE, TWO):
        make_reference(
            db,
            session,
            destiny_id,
            stage=SessionReferenceStage.MAPPED,
            coordinate={"Setting": ["Urban"]},
        )
    monkeypatch.setattr(
        routes, "get_evidence", lambda ids: [{ONE: Evidence(destiny_id=ONE)}]
    )

    body = client.get(f"/sessions/{session.id}/map/").json()

    assert len(body["mapped_evidence"]) == 1


def test_a_dimensions_artifact_that_is_not_three_is_a_clear_error(
    client, db, session, monkeypatch
):
    put_dimensions(db, session, DIMENSIONS[:2])
    monkeypatch.setattr(routes, "get_evidence", lambda ids: [])

    reply = client.get(f"/sessions/{session.id}/map/")

    assert reply.status_code == 500


def test_references_are_listed_at_every_stage_with_their_reasoning(db, client, session):
    """The record download's only source for why a reference was set aside."""
    from research_mapper.workflows.evidence_map.enums import SessionReferenceStage

    included = make_reference(db, session, ONE, stage=SessionReferenceStage.INCLUDED)
    included.screening = {"include": True, "reasoning": "reports uptake", "criteria_version": 2}
    included.coordinate = {"Setting": ["School"]}
    excluded = make_reference(db, session, TWO, stage=SessionReferenceStage.EXCLUDED)
    excluded.screening = {"include": False, "reasoning": "high-income only", "criteria_version": 2}
    db.commit()

    body = client.get(f"/sessions/{session.id}/references/").json()

    assert {row["stage"] for row in body} == {"included", "excluded"}
    by_id = {row["destiny_id"]: row for row in body}
    assert by_id[str(TWO)]["screening"]["reasoning"] == "high-income only"
    assert by_id[str(TWO)]["coordinate"] is None
    assert by_id[str(ONE)]["coordinate"] == {"Setting": ["School"]}


def test_references_of_another_session_are_not_listed(db, client, session):
    from research_mapper.engine.models import User

    owner = db.get(User, session.user_id)
    other = make_session(db, owner, question="Something else?")
    make_reference(db, other, ONE)
    make_reference(db, session, TWO)

    body = client.get(f"/sessions/{session.id}/references/").json()

    assert [row["destiny_id"] for row in body] == [str(TWO)]
