import uuid

import dspy
import pytest

from factories import make_operation, make_session, make_user
from research_mapper.engine.models import Operation
from research_mapper.engine.views import Progress
from research_mapper.models.common import Evidence
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.context import EvidenceMapContext
from research_mapper.workflows.evidence_map.models import SessionReference
from research_mapper.workflows.evidence_map.steps import retrieve

ONE = uuid.UUID("11111111-1111-4111-8111-111111111111")
TWO = uuid.UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture
def ctx(db, session_factory):
    user = make_user(db)
    session = make_session(db, user)
    return EvidenceMapContext(make_operation(db, session, user).id, session_factory)


def current_progress(db, ctx) -> Progress:
    db.expire_all()
    operation = db.get(Operation, ctx.operation_id)
    assert operation is not None
    return operation.progress


def prediction(*destiny_ids) -> dspy.Prediction:
    return dspy.Prediction(
        evidence=[Evidence(destiny_id=i) for i in destiny_ids],
        search_summary="summary",
        stopping_reason="done",
        reasoning="because",
    )


def test_sparse_retrieval_records_a_reference_per_query(ctx, db, monkeypatch):
    ctx.write_artifact(
        artifacts.SEARCH_QUERIES,
        artifacts.SearchQueries.model_validate(
            {"queries": [{"query": "a"}, {"query": "b"}]}
        ),
    )
    by_query = {"a": prediction(ONE), "b": prediction(ONE, TWO)}
    monkeypatch.setattr(
        retrieve.EvidenceRetriever,
        "__call__",
        lambda self, search_query, **_: by_query[search_query.query],
    )

    result = retrieve.RetrieveSparseEvidence().run(
        ctx, retrieve.RetrieveSparseEvidenceParams()
    )

    assert result == {"queries": 2, "failed": 0, "references": 2}
    stored = db.query(SessionReference).filter_by(destiny_id=ONE).one()
    assert [p["query"] for p in stored.provenance] == ["a", "b"]


def test_sparse_retrieval_skips_failed_batch_items(ctx, db, monkeypatch):
    ctx.write_artifact(
        artifacts.SEARCH_QUERIES,
        artifacts.SearchQueries.model_validate(
            {"queries": [{"query": "a"}, {"query": "b"}]}
        ),
    )

    def one_query_fails(self, search_query, **_):
        if search_query.query == "a":
            raise RuntimeError("DESTINY is down")
        return prediction(ONE)

    monkeypatch.setattr(retrieve.EvidenceRetriever, "__call__", one_query_fails)

    result = retrieve.RetrieveSparseEvidence().run(
        ctx, retrieve.RetrieveSparseEvidenceParams()
    )

    assert result == {"queries": 2, "failed": 1, "references": 1}
    progress = current_progress(db, ctx)
    assert (progress.done, progress.failed) == (2, 1)


def test_retrieval_fails_without_its_upstream_artifact(ctx):
    with pytest.raises(LookupError):
        retrieve.RetrieveSparseEvidence().run(
            ctx, retrieve.RetrieveSparseEvidenceParams()
        )


def test_concept_retrieval_uses_the_community_the_filters_were_built_for(
    ctx, db, monkeypatch
):
    ctx.write_artifact(
        artifacts.CONCEPT_FILTERS,
        artifacts.ConceptFilters.model_validate(
            {
                "community": "esea",
                "groups": [
                    {
                        "scheme": "topic",
                        "concept_local_refs": ["c1"],
                        "reason": "relevant",
                        "labels": ["Schools"],
                        "concepts": ["https://vocab.example/c1"],
                    }
                ],
            }
        ),
    )
    seen = {}

    def fake_call(self, **kwargs):
        seen.update(kwargs)
        return prediction(ONE)

    monkeypatch.setattr(retrieve.ConceptEvidenceRetriever, "__call__", fake_call)

    result = retrieve.RetrieveConceptEvidence().run(
        ctx, retrieve.RetrieveConceptEvidenceParams()
    )

    assert result == {"filter_groups": 1, "references": 1}
    assert seen["community"] == "esea"
    assert seen["concepts"] == [["https://vocab.example/c1"]]
    stored = db.query(SessionReference).filter_by(destiny_id=ONE).one()
    assert stored.provenance[0]["mode"] == "taxonomy"


def test_concept_retrieval_fails_clearly_until_its_producer_exists(ctx):
    """generate_concept_filters is Phase 5; until then this is the failure to expect."""
    with pytest.raises(LookupError, match=artifacts.ArtifactType.CONCEPT_FILTERS):
        retrieve.RetrieveConceptEvidence().run(
            ctx, retrieve.RetrieveConceptEvidenceParams()
        )
