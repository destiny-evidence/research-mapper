"""Fetching evidence from DESTINY."""

import builtins
import logging
from collections.abc import Iterable
from typing import ClassVar, Protocol
from uuid import UUID

import dspy
from pydantic import BaseModel

from research_mapper.engine.registry import Step
from research_mapper.models.common import Evidence, UserQuery
from research_mapper.models.taxonomy_search import ConceptFilterGroup
from research_mapper.taxonomy import RepoCommunity
from research_mapper.workflows.evidence_map.context import EvidenceMapContext
from research_mapper.workflows.evidence_map.fanout import ProgressTracker
from research_mapper.workflows.evidence_map.pipeline import (
    ConceptEvidenceRetriever,
    EvidenceRetriever,
)
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.views import RefRow

logger = logging.getLogger(__name__)

RETRIEVING = "retrieving evidence"

SPARSE_MODE = "sparse"
TAXONOMY_MODE = "taxonomy"


class Retrieval(Protocol):
    """What both retrievers put on a Prediction."""

    evidence: list[Evidence]
    search_summary: str
    stopping_reason: str


def _record(
    ctx: EvidenceMapContext, evidence: Iterable[Evidence], provenance: dict
) -> set[UUID]:
    """Record retrieved evidence against this session, and return the ids seen."""
    rows = [RefRow(item.destiny_id, provenance) for item in evidence]
    ctx.record_references(rows)
    return {row.destiny_id for row in rows}


class RetrieveSparseEvidenceParams(BaseModel):
    """Inputs to retrieve_sparse_evidence."""


class RetrieveSparseEvidence(Step[RetrieveSparseEvidenceParams, EvidenceMapContext]):
    """Retrieve evidence from DESTINY for each search query the user chose."""

    type: ClassVar[str] = "retrieve_sparse_evidence"
    Params: ClassVar[builtins.type[BaseModel]] = RetrieveSparseEvidenceParams

    def run(
        self, ctx: EvidenceMapContext, params: RetrieveSparseEvidenceParams
    ) -> dict:
        """Retrieve evidence over the sparse queries."""
        queries = ctx.require_artifact(artifacts.SEARCH_QUERIES).queries
        user_query = UserQuery(query=ctx.research_session.question)
        community = RepoCommunity(ctx.research_session.community)
        tracker = ProgressTracker(ctx, len(queries), note=RETRIEVING)
        tracker.start()

        examples = [
            dspy.Example(
                user_query=user_query, search_query=query, community=community
            ).with_inputs("user_query", "search_query", "community")
            for query in queries
        ]
        predictions: list[Retrieval | None] = tracker.fan_out(
            EvidenceRetriever(), examples
        )

        retrieved: set[UUID] = set()
        for query, prediction in zip(queries, predictions, strict=True):
            if prediction is None:
                logger.warning("retrieval failed for query %s", query)
                continue
            retrieved |= _record(
                ctx,
                prediction.evidence,
                {
                    "mode": SPARSE_MODE,
                    "query": query.query,
                    "search_summary": prediction.search_summary,
                    "stopping_reason": prediction.stopping_reason,
                },
            )

        return {
            "queries": len(queries),
            "failed": tracker.failed,
            "references": len(retrieved),
        }


class RetrieveConceptEvidenceParams(BaseModel):
    """Inputs to retrieve_concept_evidence."""


class RetrieveConceptEvidence(Step[RetrieveConceptEvidenceParams, EvidenceMapContext]):
    """Retrieve evidence from DESTINY for the concept filters the user chose."""

    type: ClassVar[str] = "retrieve_concept_evidence"
    Params: ClassVar[builtins.type[BaseModel]] = RetrieveConceptEvidenceParams

    def run(
        self, ctx: EvidenceMapContext, params: RetrieveConceptEvidenceParams
    ) -> dict:
        """Retrieve evidence over the chosen filter groups."""
        filters = ctx.require_artifact(artifacts.CONCEPT_FILTERS)
        groups, community = filters.groups, filters.community
        ctx.progress(0, 1, note=RETRIEVING)

        prediction: Retrieval = ConceptEvidenceRetriever()(
            user_query=UserQuery(query=ctx.research_session.question),
            community=community,
            filter_groups=[
                ConceptFilterGroup(
                    scheme=group.scheme,
                    concept_local_refs=group.concept_local_refs,
                    reason=group.reason,
                )
                for group in groups
            ],
            concepts=[group.concepts for group in groups],
        )
        retrieved = _record(
            ctx,
            prediction.evidence,
            {
                "mode": TAXONOMY_MODE,
                "community": community.value,
                "filters": [
                    {"scheme": group.scheme, "labels": group.labels} for group in groups
                ],
                "search_summary": prediction.search_summary,
                "stopping_reason": prediction.stopping_reason,
            },
        )
        ctx.progress(1, 1, note="retrieved")
        return {"filter_groups": len(groups), "references": len(retrieved)}
