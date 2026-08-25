import uuid

import dspy
import pytest

from factories import make_operation, make_reference, make_session, make_user
from research_mapper.models.common import Evidence
from research_mapper.models.mapping import (
    DimensionSubTopic,
    MappingDimensionWithSubTopics,
)
from research_mapper.models.taxonomy_search import Concept, IndexedVocab
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.context import EvidenceMapContext
from research_mapper.workflows.evidence_map.enums import SessionReferenceStage
from research_mapper.workflows.evidence_map.models import SessionReference
from research_mapper.workflows.evidence_map.steps import taxonomy_mapping
from research_mapper.workflows.evidence_map.steps.mapping import NothingToMap

ONE = uuid.UUID("11111111-1111-4111-8111-111111111111")
TWO = uuid.UUID("22222222-2222-4222-8222-222222222222")

CONCEPTS = [
    Concept(local_ref="C0", scheme="Setting", label="School"),
    Concept(local_ref="C1", scheme="Population", label="Teens"),
    Concept(local_ref="C2", scheme="Outcome", label="Uptake"),
    Concept(local_ref="C3", scheme="Setting", label="Clinic"),
    Concept(local_ref="C4", scheme="Design", label="Cohort"),
]
IRI = {concept.local_ref: f"https://x.test/{concept.local_ref}" for concept in CONCEPTS}
VOCAB = IndexedVocab(concepts=CONCEPTS, local_ref_to_iri=IRI)


@pytest.fixture
def session(db):
    return make_session(db, make_user(db))


@pytest.fixture
def ctx(db, session, session_factory):
    operation = make_operation(
        db, session, make_user(db, "runner"), type="generate_taxonomy_map"
    )
    return EvidenceMapContext(operation.id, session_factory)


def taxonomy(monkeypatch):
    monkeypatch.setattr(taxonomy_mapping, "get_taxonomy", lambda community: {})
    monkeypatch.setattr(taxonomy_mapping, "build_concept_index", lambda vocab: VOCAB)


def annotate(monkeypatch, **by_reference):
    """Stand in for DESTINY hydration: each reference's known concept local_refs."""

    def fake_get_evidence(reference_ids):
        yield {
            destiny_id: Evidence(
                destiny_id=destiny_id,
                title=str(destiny_id),
                known_concepts=[IRI[ref] for ref in refs],
            )
            for destiny_id, refs in (
                (uuid.UUID(key), value) for key, value in by_reference.items()
            )
            if destiny_id in set(reference_ids)
        }

    monkeypatch.setattr(taxonomy_mapping, "get_evidence", fake_get_evidence)


def dimensions(monkeypatch, *names) -> list:
    """Make the scheme generator return these schemes, and record what it was offered."""
    offered = []

    def fake_call(self, user_query, indexed_vocab, available_schemes):
        offered.append(available_schemes)
        built = [
            MappingDimensionWithSubTopics(
                name=name,
                description=f"Taxonomy scheme: {name}",
                subtopics=[
                    DimensionSubTopic(name=concept.label, description="")
                    for concept in CONCEPTS
                    if concept.scheme == name
                ],
            )
            for name in names
        ]
        return dspy.Prediction(
            dimension1=built[0],
            dimension2=built[1],
            dimension3=built[2],
            reasoning="because",
        )

    monkeypatch.setattr(
        taxonomy_mapping.TaxonomySchemeDimensionGenerator, "__call__", fake_call
    )
    return offered


def test_references_are_placed_from_their_own_annotations(
    db, ctx, session, monkeypatch
):
    make_reference(db, session, ONE, stage=SessionReferenceStage.INCLUDED)
    make_reference(db, session, TWO, stage=SessionReferenceStage.INCLUDED)
    taxonomy(monkeypatch)
    annotate(
        monkeypatch,
        **{
            str(ONE): ["C0", "C3", "C1", "C2"],
            str(TWO): ["C0", "C1"],  # no Outcome concept, so it cannot be placed
        },
    )
    dimensions(monkeypatch, "Setting", "Population", "Outcome")

    result = taxonomy_mapping.GenerateTaxonomyMap().run(
        ctx, taxonomy_mapping.GenerateTaxonomyMapParams()
    )

    assert result["mapped"] == 1
    assert result["dropped"] == 1
    placed = db.query(SessionReference).filter_by(destiny_id=ONE).one()
    assert placed.stage == SessionReferenceStage.MAPPED
    assert placed.coordinate == {
        "Setting": ["School", "Clinic"],
        "Population": ["Teens"],
        "Outcome": ["Uptake"],
    }
    written = ctx.require_artifact(artifacts.DIMENSIONS).dimensions
    assert [dimension.name for dimension in written] == [
        "Setting",
        "Population",
        "Outcome",
    ]


def test_only_schemes_the_evidence_carries_are_offered(db, ctx, session, monkeypatch):
    make_reference(db, session, ONE, stage=SessionReferenceStage.INCLUDED)
    taxonomy(monkeypatch)
    annotate(monkeypatch, **{str(ONE): ["C0", "C1", "C2"]})
    offered = dimensions(monkeypatch, "Setting", "Population", "Outcome")

    taxonomy_mapping.GenerateTaxonomyMap().run(
        ctx, taxonomy_mapping.GenerateTaxonomyMapParams()
    )

    # "Design" is in the taxonomy but nothing is annotated against it.
    assert offered == [["Outcome", "Population", "Setting"]]


def test_fewer_than_three_schemes_stops_the_step(db, ctx, session, monkeypatch):
    make_reference(db, session, ONE, stage=SessionReferenceStage.INCLUDED)
    taxonomy(monkeypatch)
    annotate(monkeypatch, **{str(ONE): ["C0", "C1"]})

    with pytest.raises(taxonomy_mapping.NotEnoughSchemes, match="2 taxonomy scheme"):
        taxonomy_mapping.GenerateTaxonomyMap().run(
            ctx, taxonomy_mapping.GenerateTaxonomyMapParams()
        )


def test_an_empty_funnel_is_not_a_map(db, ctx, session, monkeypatch):
    make_reference(db, session, ONE, stage=SessionReferenceStage.EXCLUDED)
    taxonomy(monkeypatch)

    with pytest.raises(NothingToMap):
        taxonomy_mapping.GenerateTaxonomyMap().run(
            ctx, taxonomy_mapping.GenerateTaxonomyMapParams()
        )
