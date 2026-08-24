import uuid

import dspy
import pytest

from factories import make_operation, make_reference, make_session, make_user
from research_mapper.engine.context import NeedsInput
from research_mapper.engine.enums import DecisionType
from research_mapper.engine.models import Decision
from research_mapper.models.common import Evidence
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.context import EvidenceMapContext
from research_mapper.workflows.evidence_map.enums import SessionReferenceStage
from research_mapper.workflows.evidence_map.models import SessionReference
from research_mapper.workflows.evidence_map.steps import mapping

ONE = uuid.UUID("11111111-1111-4111-8111-111111111111")
TWO = uuid.UUID("22222222-2222-4222-8222-222222222222")

AXES = [
    {"name": "Setting", "description": "where"},
    {"name": "Population", "description": "who"},
    {"name": "Outcome", "description": "what"},
]
SUBTOPICS = {
    "Setting": [{"name": "School", "description": "in schools"}],
    "Population": [{"name": "Teens", "description": "13-19"}],
    "Outcome": [{"name": "Uptake", "description": "vaccine uptake"}],
}


@pytest.fixture
def session(db):
    return make_session(db, make_user(db))


@pytest.fixture
def operation(db, session):
    return make_operation(db, session, make_user(db, "runner"), type="generate_map")


@pytest.fixture
def ctx(operation, session_factory):
    return EvidenceMapContext(operation.id, session_factory)


def answer(db, operation, key, value):
    db.add(
        Decision(
            research_session_id=operation.research_session_id,
            operation_id=operation.id,
            type=DecisionType.EDIT_LIST,
            key=key,
            prompt="edit",
            answer=value,
        )
    )
    db.commit()


def with_subtopics(names=("Setting", "Population", "Outcome")) -> list[dict]:
    return [
        {**axis, "subtopics": SUBTOPICS[axis["name"]]}
        for axis in AXES
        if axis["name"] in names
    ]


def test_dimensions_are_suggested_then_edited(db, ctx, operation, monkeypatch):
    def fake_call(self, **_):
        return dspy.Prediction(
            dimension1=AXES[0], dimension2=AXES[1], dimension3=AXES[2], reasoning="why"
        )

    monkeypatch.setattr(mapping.DimensionGenerator, "__call__", fake_call)

    with pytest.raises(NeedsInput):
        mapping.GenerateMapDimensions().run(ctx, mapping.GenerateMapDimensionsParams())

    spec = ctx.pending_decisions["edit_dimensions"]
    assert spec.type == "edit_list"
    assert spec.constraints == {"min": 3, "max": 3, "allow_new": True}
    assert [option["value"] for option in spec.options] == AXES

    renamed = [{"name": "Site", "description": "where"}, AXES[1], AXES[2]]
    answer(db, operation, "edit_dimensions", renamed)
    result = mapping.GenerateMapDimensions().run(
        ctx, mapping.GenerateMapDimensionsParams()
    )

    assert result == {"dimensions": 3, "version": 1}
    stored = ctx.get_artifact(artifacts.MAP_DIMENSIONS)
    assert stored is not None
    assert [d.name for d in stored.dimensions] == ["Site", "Population", "Outcome"]


def test_subtopics_are_generated_per_dimension_then_edited(
    db, ctx, operation, monkeypatch
):
    ctx.write_artifact(
        artifacts.MAP_DIMENSIONS,
        artifacts.MapDimensions.model_validate({"dimensions": AXES}),
    )

    def fake_call(self, dimension, other_dimensions, **_):
        assert [d.name for d in other_dimensions] != [dimension.name]
        return dspy.Prediction(subtopics=SUBTOPICS[dimension.name], reasoning="why")

    monkeypatch.setattr(mapping.SubtopicGenerator, "__call__", fake_call)

    with pytest.raises(NeedsInput):
        mapping.GenerateMapSubtopics().run(ctx, mapping.GenerateMapSubtopicsParams())

    assert set(ctx.pending_decisions) == {
        f"edit_subtopics:{axis['name']}" for axis in AXES
    }

    for axis in AXES:
        edited = SUBTOPICS[axis["name"]]
        if axis["name"] == "Setting":
            edited = edited + [{"name": "Clinic", "description": "added by hand"}]
        answer(db, operation, f"edit_subtopics:{axis['name']}", edited)

    result = mapping.GenerateMapSubtopics().run(
        ctx, mapping.GenerateMapSubtopicsParams()
    )

    assert result == {"dimensions": 3, "subtopics": 4, "version": 1}
    stored = ctx.get_artifact(artifacts.DIMENSIONS)
    assert stored is not None
    assert [s.name for s in stored.dimensions[0].subtopics] == ["School", "Clinic"]


def test_a_dimension_without_subtopics_fails_the_operation(db, ctx, monkeypatch):
    """The mapping signature can't be built for it, so narrowing the map silently is worse."""
    ctx.write_artifact(
        artifacts.MAP_DIMENSIONS,
        artifacts.MapDimensions.model_validate({"dimensions": AXES}),
    )

    def fake_call(self, dimension, **_):
        if dimension.name == "Outcome":
            raise RuntimeError("the model fell over")
        return dspy.Prediction(subtopics=SUBTOPICS[dimension.name], reasoning="why")

    monkeypatch.setattr(mapping.SubtopicGenerator, "__call__", fake_call)

    with pytest.raises(RuntimeError, match="Outcome"):
        mapping.GenerateMapSubtopics().run(ctx, mapping.GenerateMapSubtopicsParams())

    assert ctx.get_artifact(artifacts.SUGGESTED_DIMENSION_SUBTOPICS) is None


def hydrate(monkeypatch, *destiny_ids) -> None:
    def fake_get_evidence(reference_ids):
        wanted = [i for i in destiny_ids if i in set(reference_ids)]
        if wanted:
            yield {i: Evidence(destiny_id=i, title=f"paper {i}") for i in wanted}

    monkeypatch.setattr(mapping, "get_evidence", fake_get_evidence)


def test_only_included_references_are_placed_on_the_map(db, ctx, session, monkeypatch):
    ctx.write_artifact(
        artifacts.DIMENSIONS,
        artifacts.Dimensions.model_validate({"dimensions": with_subtopics()}),
    )
    make_reference(db, session, ONE, stage=SessionReferenceStage.INCLUDED)
    make_reference(db, session, TWO, stage=SessionReferenceStage.EXCLUDED)
    hydrate(monkeypatch, ONE, TWO)

    def fake_call(self, **_):
        return dspy.Prediction(
            dimension1_subtopic="School",
            dimension2_subtopic="Teens",
            dimension3_subtopic="Uptake",
            reasoning="why",
        )

    monkeypatch.setattr(mapping.EvidenceMapper, "__call__", fake_call)

    assert mapping.GenerateMap().run(ctx, mapping.GenerateMapParams()) == {
        "mapped": 1,
        "failed": 0,
    }

    rows = {r.destiny_id: r for r in db.query(SessionReference).all()}
    assert rows[ONE].stage == SessionReferenceStage.MAPPED
    assert rows[ONE].coordinate == {
        "Setting": ["School"],
        "Population": ["Teens"],
        "Outcome": ["Uptake"],
    }
    assert rows[TWO].coordinate is None


def test_a_failed_mapping_leaves_the_reference_unmapped(db, ctx, session, monkeypatch):
    ctx.write_artifact(
        artifacts.DIMENSIONS,
        artifacts.Dimensions.model_validate({"dimensions": with_subtopics()}),
    )
    make_reference(db, session, ONE, stage=SessionReferenceStage.INCLUDED)
    hydrate(monkeypatch, ONE)
    monkeypatch.setattr(
        mapping.EvidenceMapper,
        "__call__",
        lambda self, **_: (_ for _ in ()).throw(RuntimeError("no")),
    )

    assert mapping.GenerateMap().run(ctx, mapping.GenerateMapParams()) == {
        "mapped": 0,
        "failed": 1,
    }
    row = db.query(SessionReference).filter_by(destiny_id=ONE).one()
    assert row.stage == SessionReferenceStage.INCLUDED


def test_mapping_refuses_a_dimension_set_it_cannot_map_against(db, ctx):
    ctx.write_artifact(
        artifacts.DIMENSIONS,
        artifacts.Dimensions.model_validate(
            {"dimensions": with_subtopics(names=("Setting", "Population"))}
        ),
    )
    with pytest.raises(ValueError, match="3 dimensions"):
        mapping.GenerateMap().run(ctx, mapping.GenerateMapParams())


def test_mapping_needs_its_dimensions_first(ctx):
    with pytest.raises(LookupError, match=artifacts.ArtifactType.DIMENSIONS):
        mapping.GenerateMap().run(ctx, mapping.GenerateMapParams())


def test_subtopics_need_the_chosen_dimensions_first(ctx):
    with pytest.raises(LookupError, match=artifacts.ArtifactType.MAP_DIMENSIONS):
        mapping.GenerateMapSubtopics().run(ctx, mapping.GenerateMapSubtopicsParams())


def test_the_map_route_reads_what_generate_map_wrote(db, ctx, session, monkeypatch):
    """The pipeline's end: what the steps write is what /map serves."""
    from fastapi.testclient import TestClient

    from research_mapper.api.app import app
    from research_mapper.api.deps import get_session_factory
    from research_mapper.config import init_database

    ctx.write_artifact(
        artifacts.DIMENSIONS,
        artifacts.Dimensions.model_validate({"dimensions": with_subtopics()}),
    )
    make_reference(db, session, ONE, stage=SessionReferenceStage.INCLUDED)
    hydrate(monkeypatch, ONE)
    monkeypatch.setattr(
        mapping.EvidenceMapper,
        "__call__",
        lambda self, **_: dspy.Prediction(
            dimension1_subtopic="School",
            dimension2_subtopic="Teens",
            dimension3_subtopic="Uptake",
            reasoning="why",
        ),
    )
    mapping.GenerateMap().run(ctx, mapping.GenerateMapParams())

    from research_mapper.workflows.evidence_map import routes

    monkeypatch.setattr(
        routes,
        "get_evidence",
        lambda ids: [{ONE: Evidence(destiny_id=ONE, title="paper one")}],
    )
    app.dependency_overrides[get_session_factory] = lambda: ctx._sf
    try:
        with TestClient(app) as client:
            body = client.get(f"/sessions/{session.id}/map/").json()
    finally:
        app.dependency_overrides.clear()
        init_database()

    assert [d["name"] for d in body["dimensions"]] == [
        "Setting",
        "Population",
        "Outcome",
    ]
    assert body["mapped_evidence"][0]["coordinate"] == {
        "Setting": ["School"],
        "Population": ["Teens"],
        "Outcome": ["Uptake"],
    }
