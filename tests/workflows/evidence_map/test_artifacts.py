import json

import pytest

from factories import make_operation, make_session, make_user
from research_mapper.engine.context import StepContext
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.artifacts import ArtifactType

PAYLOADS: dict[ArtifactType, dict] = {
    ArtifactType.SUGGESTED_SEARCH_QUERIES: {"queries": [{"query": "hpv AND uptake"}]},
    ArtifactType.SEARCH_QUERIES: {"queries": [{"query": "hpv AND uptake"}]},
    ArtifactType.SUGGESTED_SCREENING_CRITERIA: {
        "criteria": [{"criterion_type": "inclusion", "description": "peer reviewed"}]
    },
    ArtifactType.SCREENING_CRITERIA: {
        "criteria": [{"criterion_type": "exclusion", "description": "not english"}]
    },
    ArtifactType.SUGGESTED_CONCEPT_FILTERS: {
        "community": "esea",
        "groups": [
            {
                "scheme": "topic",
                "concept_local_refs": ["C1"],
                "reason": "relevant",
                "labels": ["Schools"],
                "concepts": ["https://vocab.example/c1"],
            }
        ],
    },
    ArtifactType.CONCEPT_FILTERS: {"community": "hpv", "groups": []},
    ArtifactType.CONCEPT_FILTER_LOOP: {
        "step": {"idx": 0, "thought": "t", "tool_name": "ask", "tool_args": {}},
        "trajectory": [["thought_0", "t"], ["tool_name_0", "ask"]],
    },
    ArtifactType.SUGGESTED_MAP_DIMENSIONS: {
        "dimensions": [{"name": "Setting", "description": "where"}]
    },
    ArtifactType.MAP_DIMENSIONS: {
        "dimensions": [{"name": "Setting", "description": "where"}]
    },
    ArtifactType.SUGGESTED_DIMENSION_SUBTOPICS: {
        "dimensions": [
            {
                "name": "Setting",
                "description": "where",
                "subtopics": [{"name": "School", "description": "in schools"}],
            }
        ]
    },
    ArtifactType.DIMENSIONS: {
        "dimensions": [
            {
                "name": "Setting",
                "description": "where",
                "subtopics": [{"name": "School", "description": "in schools"}],
            }
        ]
    },
}


@pytest.fixture
def ctx(db, session_factory):
    user = make_user(db)
    session = make_session(db, user)
    return StepContext(make_operation(db, session, user).id, session_factory)


def test_every_artifact_type_is_in_the_catalogue():
    assert set(artifacts.ARTIFACTS) == set(ArtifactType)


@pytest.mark.parametrize("name", list(ArtifactType))
def test_payloads_survive_a_round_trip_through_jsonb(name, ctx):
    """What a step writes is what the next step reads back, JSON in between."""
    spec = artifacts.ARTIFACTS[name]
    written = spec.model.model_validate(PAYLOADS[name])

    assert ctx.write_artifact(spec, written) == 1
    assert ctx.get_artifact(spec) == written
    # the write leans on the driver's serialiser, so prove the dump is really JSON.
    json.dumps(written.model_dump(mode="json"))
