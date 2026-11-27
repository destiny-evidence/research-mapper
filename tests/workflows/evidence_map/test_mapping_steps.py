import uuid

import dspy
import pytest

from factories import make_operation, make_reference, make_session, make_user
from research_mapper.engine.answers import InvalidAnswer, validate_answer
from research_mapper.engine.context import NeedsInput
from research_mapper.engine.enums import DecisionType
from research_mapper.engine.models import Decision
from research_mapper.models.common import Evidence
from research_mapper.workflows.evidence_map import artifacts, context
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
# Two each: mapping chooses between a dimension's subtopics, so a map needs at least two.
SUBTOPICS = {
    "Setting": [
        {"name": "School", "description": "in schools"},
        {"name": "Home", "description": "at home"},
    ],
    "Population": [
        {"name": "Teens", "description": "13-19"},
        {"name": "Adults", "description": "20 and over"},
    ],
    "Outcome": [
        {"name": "Uptake", "description": "vaccine uptake"},
        {"name": "Adherence", "description": "completing the course"},
    ],
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
    assert spec.constraints == {
        "min": 3,
        "max": 3,
        "allow_new": True,
        "unique": "name",
    }
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

    assert result == {"dimensions": 3, "subtopics": 7, "version": 1}
    stored = ctx.get_artifact(artifacts.DIMENSIONS)
    assert stored is not None
    assert [s.name for s in stored.dimensions[0].subtopics] == [
        "School",
        "Home",
        "Clinic",
    ]


def test_each_dimension_must_keep_two_distinct_subtopics(
    db, ctx, operation, monkeypatch
):
    """Mapping can't choose from fewer, so the edit is refused rather than every
    piece of evidence failing later at the map step."""
    ctx.write_artifact(
        artifacts.MAP_DIMENSIONS,
        artifacts.MapDimensions.model_validate({"dimensions": AXES}),
    )
    monkeypatch.setattr(
        mapping.SubtopicGenerator,
        "__call__",
        lambda self, dimension, **_: dspy.Prediction(
            subtopics=SUBTOPICS[dimension.name], reasoning="why"
        ),
    )

    with pytest.raises(NeedsInput):
        mapping.GenerateMapSubtopics().run(ctx, mapping.GenerateMapSubtopicsParams())

    spec = ctx.pending_decisions["edit_subtopics:Setting"]
    assert spec.constraints == {"min": 2, "allow_new": True, "unique": "name"}

    decision = Decision(constraints=spec.constraints, options=spec.options)
    with pytest.raises(InvalidAnswer, match="at least 2"):
        validate_answer(decision, SUBTOPICS["Setting"][:1])
    validate_answer(decision, SUBTOPICS["Setting"])
    with pytest.raises(InvalidAnswer, match="names must be unique: School"):
        validate_answer(decision, [*SUBTOPICS["Setting"], SUBTOPICS["Setting"][0]])


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


def test_references_are_mapped_a_batch_at_a_time(db, ctx, session, monkeypatch):
    ctx.write_artifact(
        artifacts.DIMENSIONS,
        artifacts.Dimensions.model_validate({"dimensions": with_subtopics()}),
    )
    ids = [uuid.uuid4() for _ in range(5)]
    for destiny_id in ids:
        make_reference(db, session, destiny_id, stage=SessionReferenceStage.INCLUDED)
    monkeypatch.setattr(context, "BATCH_SIZE", 2)
    looked_up = []

    def fake_get_evidence(reference_ids):
        looked_up.append(len(reference_ids))
        yield {i: Evidence(destiny_id=i, title=f"paper {i}") for i in reference_ids}

    monkeypatch.setattr(mapping, "get_evidence", fake_get_evidence)
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

    assert mapping.GenerateMap().run(ctx, mapping.GenerateMapParams()) == {
        "mapped": 5,
        "failed": 0,
    }
    assert looked_up == [2, 2, 1]
    stages = {r.stage for r in db.query(SessionReference).all()}
    assert stages == {SessionReferenceStage.MAPPED}


def test_what_the_coordinate_was_chosen_from_is_stored(db, ctx, session, monkeypatch):
    """Probabilities and model go in the mapping blob; the coordinate keeps its shape."""
    ctx.write_artifact(
        artifacts.DIMENSIONS,
        artifacts.Dimensions.model_validate({"dimensions": with_subtopics()}),
    )
    make_reference(db, session, ONE, stage=SessionReferenceStage.INCLUDED)
    hydrate(monkeypatch, ONE)
    probabilities = {
        "Setting": {"School": 0.9, "Clinic": 0.1},
        "Population": {"Teens": 0.7, "Adults": 0.3},
        "Outcome": {"Uptake": 0.55, "Adherence": 0.45},
    }

    def fake_call(self, **_):
        return dspy.Prediction(
            dimension1_subtopic="School",
            dimension2_subtopic="Teens",
            dimension3_subtopic="Uptake",
            reasoning="why",
            probabilities=probabilities,
            model="gpt-6-luna",
            dedicated=True,
        )

    monkeypatch.setattr(mapping.EvidenceMapper, "__call__", fake_call)

    mapping.GenerateMap().run(ctx, mapping.GenerateMapParams())

    row = db.query(SessionReference).filter_by(destiny_id=ONE).one()
    assert row.mapping["probabilities"] == probabilities
    assert row.mapping["model"] == "gpt-6-luna"
    assert row.mapping["dedicated"] is True
    assert row.coordinate == {
        "Setting": ["School"],
        "Population": ["Teens"],
        "Outcome": ["Uptake"],
    }


def test_mapping_fails_when_screening_included_nothing(db, ctx, session, monkeypatch):
    """Otherwise every step goes green and the session ends with an empty map."""
    ctx.write_artifact(
        artifacts.DIMENSIONS,
        artifacts.Dimensions.model_validate({"dimensions": with_subtopics()}),
    )
    make_reference(db, session, ONE, stage=SessionReferenceStage.EXCLUDED)
    hydrate(monkeypatch)

    with pytest.raises(mapping.NothingToMap, match="nothing to map"):
        mapping.GenerateMap().run(ctx, mapping.GenerateMapParams())


def test_mapping_again_with_everything_already_placed_is_not_an_empty_funnel(
    db, ctx, session, monkeypatch
):
    """Placed references leave INCLUDED, which must not read as `screening included nothing`."""
    ctx.write_artifact(
        artifacts.DIMENSIONS,
        artifacts.Dimensions.model_validate({"dimensions": with_subtopics()}),
    )
    make_reference(db, session, ONE, stage=SessionReferenceStage.MAPPED)
    hydrate(monkeypatch)

    assert mapping.GenerateMap().run(ctx, mapping.GenerateMapParams()) == {
        "mapped": 0,
        "failed": 0,
    }


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
    assert body["cells"] == [
        {
            "coordinate": {
                "Setting": ["School"],
                "Population": ["Teens"],
                "Outcome": ["Uptake"],
            },
            "count": 1,
        }
    ]


def test_subtopic_reasoning_is_kept_per_dimension(db, ctx, operation, monkeypatch):
    """SubtopicGenerator is a ChainOfThought fanned out one call per dimension,
    so each dimension has its own reasoning. All of them used to be dropped."""
    ctx.write_artifact(
        artifacts.MAP_DIMENSIONS,
        artifacts.MapDimensions.model_validate({"dimensions": AXES}),
    )

    def fake_call(self, dimension, **_):
        return dspy.Prediction(
            subtopics=SUBTOPICS[dimension.name],
            reasoning=f"because of {dimension.name}",
        )

    monkeypatch.setattr(mapping.SubtopicGenerator, "__call__", fake_call)

    with pytest.raises(NeedsInput):
        mapping.GenerateMapSubtopics().run(ctx, mapping.GenerateMapSubtopicsParams())

    suggested = ctx.get_artifact(artifacts.SUGGESTED_DIMENSION_SUBTOPICS)
    assert suggested.subtopic_reasoning == {
        axis["name"]: f"because of {axis['name']}" for axis in AXES
    }

    # It has to survive the user's edits too, or it is only ever visible while
    # the question is open.
    for axis in AXES:
        answer(db, operation, f"edit_subtopics:{axis['name']}", SUBTOPICS[axis["name"]])
    mapping.GenerateMapSubtopics().run(ctx, mapping.GenerateMapSubtopicsParams())

    assert ctx.get_artifact(artifacts.DIMENSIONS).subtopic_reasoning == {
        axis["name"]: f"because of {axis['name']}" for axis in AXES
    }


def test_a_map_that_dies_partway_keeps_the_pages_it_finished(
    db, ctx, session, monkeypatch
):
    """Otherwise a long map that dies near the end re-pays for all of it on the retry."""
    ctx.write_artifact(
        artifacts.DIMENSIONS,
        artifacts.Dimensions.model_validate({"dimensions": with_subtopics()}),
    )
    make_reference(db, session, ONE, stage=SessionReferenceStage.INCLUDED)
    make_reference(db, session, TWO, stage=SessionReferenceStage.INCLUDED)

    def one_page_then_trouble(_reference_ids):
        yield {ONE: Evidence(destiny_id=ONE, title="paper")}
        msg = "destiny went away"
        raise RuntimeError(msg)

    monkeypatch.setattr(mapping, "get_evidence", one_page_then_trouble)
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

    with pytest.raises(RuntimeError, match="destiny went away"):
        mapping.GenerateMap().run(ctx, mapping.GenerateMapParams())

    rows = {r.destiny_id: r.stage for r in db.query(SessionReference).all()}
    assert rows[ONE] == SessionReferenceStage.MAPPED
    assert rows[TWO] == SessionReferenceStage.INCLUDED
