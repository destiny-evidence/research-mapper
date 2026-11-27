import json
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


def put_dimensions(db, session, dimensions=DIMENSIONS, version=1) -> None:
    user = make_user(db, f"author-{version}")
    operation = make_operation(db, session, user)
    db.add(
        Artifact(
            research_session_id=session.id,
            operation_id=operation.id,
            type=ArtifactType.DIMENSIONS,
            version=version,
            payload={"dimensions": dimensions},
        )
    )
    db.commit()


def test_a_session_with_no_map_yet_is_a_404(client, session):
    assert client.get(f"/sessions/{session.id}/map/").status_code == 404


def no_destiny(monkeypatch) -> None:
    def explode(_ids):
        raise AssertionError("the map should not look anything up in DESTINY")

    monkeypatch.setattr(routes, "get_evidence", explode)


URBAN = {"Setting": ["Urban"], "Outcome": ["Mortality"], "Design": ["Cohort"]}


def test_the_map_counts_mapped_references_per_coordinate(
    client, db, session, monkeypatch
):
    put_dimensions(db, session)
    for destiny_id in (ONE, TWO):
        make_reference(
            db,
            session,
            destiny_id,
            stage=SessionReferenceStage.MAPPED,
            coordinate=URBAN,
            mapping={"dimensions_version": 1},
        )
    make_reference(db, session, uuid.uuid4(), stage=SessionReferenceStage.EXCLUDED)
    no_destiny(monkeypatch)

    body = client.get(f"/sessions/{session.id}/map/").json()

    assert [d["name"] for d in body["dimensions"]] == ["Setting", "Outcome", "Design"]
    assert body["cells"] == [{"coordinate": URBAN, "count": 2}]
    assert body["total"] == 2, "only mapped references are counted"


def test_a_reference_in_several_subtopics_is_one_reference(
    client, db, session, monkeypatch
):
    """A taxonomy reference annotated with two concepts in one scheme sits in both
    subtopics, but its coordinate is still counted once."""
    put_dimensions(db, session)
    both = {**URBAN, "Outcome": ["Mortality", "Morbidity"]}
    make_reference(
        db,
        session,
        ONE,
        stage=SessionReferenceStage.MAPPED,
        coordinate=both,
        mapping={"dimensions_version": 1},
    )
    make_reference(
        db,
        session,
        TWO,
        stage=SessionReferenceStage.MAPPED,
        coordinate=URBAN,
        mapping={"dimensions_version": 1},
    )
    no_destiny(monkeypatch)

    body = client.get(f"/sessions/{session.id}/map/").json()

    by_outcome = {
        tuple(cell["coordinate"]["Outcome"]): cell["count"] for cell in body["cells"]
    }
    assert by_outcome == {("Mortality", "Morbidity"): 1, ("Mortality",): 1}
    assert body["total"] == 2


def test_coordinates_from_older_dimensions_are_left_out_of_the_map(
    client, db, session, monkeypatch
):
    """Their subtopics may no longer exist, so they would inflate the totals."""
    put_dimensions(db, session, version=1)
    put_dimensions(db, session, version=2)
    make_reference(
        db,
        session,
        ONE,
        stage=SessionReferenceStage.MAPPED,
        coordinate={"Setting": ["Rural"]},
        mapping={"dimensions_version": 1},
    )
    make_reference(
        db,
        session,
        TWO,
        stage=SessionReferenceStage.MAPPED,
        coordinate={"Setting": ["Urban"]},
        mapping={"dimensions_version": 2},
    )
    no_destiny(monkeypatch)

    body = client.get(f"/sessions/{session.id}/map/").json()

    assert body["cells"] == [{"coordinate": {"Setting": ["Urban"]}, "count": 1}]


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
    included.screening = {
        "include": True,
        "reasoning": "reports uptake",
        "criteria_version": 2,
    }
    included.coordinate = {"Setting": ["School"]}
    excluded = make_reference(db, session, TWO, stage=SessionReferenceStage.EXCLUDED)
    excluded.screening = {
        "include": False,
        "reasoning": "high-income only",
        "criteria_version": 2,
    }
    db.commit()

    body = client.get(f"/sessions/{session.id}/references/").json()["items"]

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

    body = client.get(f"/sessions/{session.id}/references/").json()["items"]

    assert [row["destiny_id"] for row in body] == [str(TWO)]


def test_references_carry_bibliographic_detail_when_asked(
    db, client, session, monkeypatch
):
    make_reference(db, session, ONE, stage=SessionReferenceStage.INCLUDED)
    monkeypatch.setattr(
        routes,
        "get_evidence",
        lambda ids: [{ONE: Evidence(destiny_id=ONE, title="A", year=2019)}],
    )

    plain = client.get(f"/sessions/{session.id}/references/").json()["items"]
    hydrated = client.get(
        f"/sessions/{session.id}/references/?include_evidence=true"
    ).json()["items"]

    assert plain[0]["evidence"] is None, "the lookup is opt-in"
    assert hydrated[0]["evidence"]["title"] == "A"
    assert hydrated[0]["evidence"]["year"] == 2019


def test_a_reference_destiny_no_longer_returns_is_still_listed(
    db, client, session, monkeypatch
):
    """Unlike the map: dropping it would understate the corpus being audited."""
    make_reference(db, session, ONE, stage=SessionReferenceStage.EXCLUDED)
    make_reference(db, session, TWO, stage=SessionReferenceStage.EXCLUDED)
    monkeypatch.setattr(
        routes, "get_evidence", lambda ids: [{ONE: Evidence(destiny_id=ONE)}]
    )

    body = client.get(
        f"/sessions/{session.id}/references/?include_evidence=true"
    ).json()["items"]

    assert {row["destiny_id"] for row in body} == {str(ONE), str(TWO)}
    body.sort(key=lambda row: row["destiny_id"])
    assert body[1]["evidence"] is None


# ---------------------------------------------------------------------------
# Paging: a view's references a page at a time, with its counts.
# ---------------------------------------------------------------------------


def page(client, session, **params):
    reply = client.get(f"/sessions/{session.id}/references/", params=params)
    assert reply.status_code == 200, reply.text
    return reply.json()


def test_pages_walk_every_reference_exactly_once(db, client, session):
    ids = {uuid.uuid4() for _ in range(7)}
    for destiny_id in ids:
        make_reference(db, session, destiny_id)

    seen, after, sizes = [], None, []
    while True:
        params = {"limit": 3, **({"after": after} if after else {})}
        body = page(client, session, **params)
        sizes.append(len(body["items"]))
        seen += [row["destiny_id"] for row in body["items"]]
        after = body["next"]
        if after is None:
            break

    assert sizes == [3, 3, 1]
    assert sorted(seen) == sorted(str(i) for i in ids)
    assert body["total"] == body["matched"] == 7


def test_only_the_page_is_looked_up_in_destiny(db, client, session, monkeypatch):
    for _ in range(5):
        make_reference(db, session, uuid.uuid4())
    looked_up = []

    def fake_get_evidence(ids):
        looked_up.append(len(ids))
        yield {i: Evidence(destiny_id=i, title="t") for i in ids}

    monkeypatch.setattr(routes, "get_evidence", fake_get_evidence)

    body = page(client, session, limit=2, include_evidence="true")

    assert looked_up == [2]
    assert all(row["evidence"]["title"] == "t" for row in body["items"])


def test_a_page_with_evidence_is_at_most_one_lookup(client, session):
    reply = client.get(
        f"/sessions/{session.id}/references/",
        params={"limit": 101, "include_evidence": "true"},
    )
    assert reply.status_code == 422
    assert (
        client.get(
            f"/sessions/{session.id}/references/", params={"limit": 1001}
        ).status_code
        == 422
    )


def screening(include: bool, model: str | None = None, dedicated=None) -> dict:
    return {
        "include": include,
        "reasoning": "r",
        "model": model,
        "dedicated": dedicated,
    }


def test_screening_buckets_by_verdict_whatever_the_stage(db, client, session):
    """A mapped reference with no screening blob, or one that failed mapping after
    being screened in, still reads as screening left it."""
    make_reference(db, session, uuid.uuid4(), stage=SessionReferenceStage.GATHERED)
    make_reference(
        db,
        session,
        uuid.uuid4(),
        stage=SessionReferenceStage.EXCLUDED,
        screening=screening(False),
    )
    make_reference(db, session, uuid.uuid4(), stage=SessionReferenceStage.MAPPED)
    make_reference(
        db,
        session,
        uuid.uuid4(),
        stage=SessionReferenceStage.FAILED,
        screening=screening(True),
    )
    make_reference(db, session, uuid.uuid4(), stage=SessionReferenceStage.FAILED)

    body = page(client, session, view="screening")

    assert body["buckets"] == [
        {"bucket": "included", "count": 2},
        {"bucket": "excluded", "count": 1},
        {"bucket": "not screened", "count": 1},
        {"bucket": "failed", "count": 1},
    ]
    included = page(client, session, view="screening", bucket="included")
    assert included["matched"] == 2
    assert included["total"] == 5


def test_mapping_shows_only_what_screening_kept_bucketed_by_placement(
    db, client, session
):
    make_reference(
        db,
        session,
        uuid.uuid4(),
        stage=SessionReferenceStage.EXCLUDED,
        screening=screening(False),
    )
    make_reference(
        db,
        session,
        uuid.uuid4(),
        stage=SessionReferenceStage.INCLUDED,
        screening=screening(True),
    )
    make_reference(
        db,
        session,
        uuid.uuid4(),
        stage=SessionReferenceStage.MAPPED,
        screening=screening(True),
    )

    body = page(client, session, view="mapping")

    assert body["total"] == 2
    assert body["buckets"] == [
        {"bucket": "mapped", "count": 1},
        {"bucket": "not mapped", "count": 1},
    ]


def test_retrieval_views_show_what_each_mode_found(db, client, session):
    make_reference(db, session, ONE, provenance=[{"mode": "sparse", "query": "q"}])
    make_reference(db, session, TWO, provenance=[{"mode": "taxonomy", "filters": []}])

    sparse = page(client, session, view="sparse")
    taxonomy = page(client, session, view="taxonomy")

    assert [row["destiny_id"] for row in sparse["items"]] == [str(ONE)]
    assert [row["destiny_id"] for row in taxonomy["items"]] == [str(TWO)]
    assert sparse["buckets"] == []
    assert (
        client.get(
            f"/sessions/{session.id}/references/",
            params={"view": "sparse", "bucket": "mapped"},
        ).status_code
        == 422
    )


def test_a_cell_narrows_to_the_references_in_it(db, client, session):
    """A reference in two subtopics of one dimension is in both cells."""
    make_reference(
        db,
        session,
        ONE,
        stage=SessionReferenceStage.MAPPED,
        coordinate={"Setting": ["Urban", "Rural"], "Outcome": ["Mortality"]},
    )
    make_reference(
        db,
        session,
        TWO,
        stage=SessionReferenceStage.MAPPED,
        coordinate={"Setting": ["Urban"], "Outcome": ["Morbidity"]},
    )

    def ids_in(*terms):
        body = page(client, session, cell=json.dumps([list(t) for t in terms]))
        return {row["destiny_id"] for row in body["items"]}

    assert ids_in(("Setting", "Urban")) == {str(ONE), str(TWO)}
    assert ids_in(("Setting", "Rural")) == {str(ONE)}
    assert ids_in(("Setting", "Urban"), ("Outcome", "Morbidity")) == {str(TWO)}
    assert (
        client.get(
            f"/sessions/{session.id}/references/", params={"cell": "not json"}
        ).status_code
        == 422
    )


def test_a_view_names_the_models_that_decided_it(db, client, session):
    make_reference(
        db,
        session,
        uuid.uuid4(),
        stage=SessionReferenceStage.INCLUDED,
        screening=screening(True, "gpt-6-luna", True),
    )
    make_reference(
        db,
        session,
        uuid.uuid4(),
        stage=SessionReferenceStage.EXCLUDED,
        screening=screening(False, "gpt-6-luna", True),
    )
    make_reference(
        db,
        session,
        uuid.uuid4(),
        stage=SessionReferenceStage.EXCLUDED,
        screening=screening(False, "gpt-chat", False),
    )
    make_reference(
        db,
        session,
        uuid.uuid4(),
        stage=SessionReferenceStage.EXCLUDED,
        screening=screening(False),
    )

    body = page(client, session, view="screening")

    assert body["decided"] == [
        {"model": "gpt-6-luna", "dedicated": True},
        {"model": "gpt-chat", "dedicated": False},
    ]
    assert page(client, session, view="all")["decided"] == []
