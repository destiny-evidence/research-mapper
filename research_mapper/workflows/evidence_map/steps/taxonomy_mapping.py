"""Building the map from the taxonomy's own schemes."""

import builtins
from typing import ClassVar

from pydantic import BaseModel

from research_mapper.engine.registry import Step
from research_mapper.models.common import IRI, UserQuery
from research_mapper.models.mapping import MappingDimensionWithSubTopics
from research_mapper.models.taxonomy_search import Concept
from research_mapper.modules.taxonomy_mapping import TaxonomySchemeDimensionGenerator
from research_mapper.taxonomy import RepoCommunity, build_concept_index, get_graph
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.context import EvidenceMapContext
from research_mapper.workflows.evidence_map.enums import SessionReferenceStage
from research_mapper.workflows.evidence_map.hydrate import get_evidence
from research_mapper.workflows.evidence_map.steps.mapping import NothingToMap
from research_mapper.workflows.evidence_map.views import CoordinateRow


class NotEnoughSchemes(Exception):
    """The evidence carries too few taxonomy schemes to build a map from."""


class GenerateTaxonomyMapParams(BaseModel):
    """Inputs to generate_taxonomy_map."""


class GenerateTaxonomyMap(Step[GenerateTaxonomyMapParams, EvidenceMapContext]):
    """Map included references along the taxonomy's own schemes."""

    type: ClassVar[str] = "generate_taxonomy_map"
    Params: ClassVar[builtins.type[BaseModel]] = GenerateTaxonomyMapParams

    def run(self, ctx: EvidenceMapContext, params: GenerateTaxonomyMapParams) -> dict:
        """Pick three schemes, then place each reference from its own annotations."""
        references = ctx.references(SessionReferenceStage.INCLUDED)
        if not references:
            msg = "screening included no evidence, so there is nothing to map"
            raise NothingToMap(msg)

        community = RepoCommunity(ctx.research_session.community)
        indexed = build_concept_index(get_graph(community))
        by_iri = {
            indexed.local_ref_to_iri[concept.local_ref]: concept
            for concept in indexed.concepts
        }

        annotations = {
            item.destiny_id: [iri for iri in item.known_concepts if iri in by_iri]
            for page in get_evidence([r.destiny_id for r in references])
            for item in page.values()
        }

        # A scheme nothing is annotated against would be a useless axis, so the LLM only
        # gets to choose from the ones actually present.
        schemes = sorted(
            {by_iri[iri].scheme for iris in annotations.values() for iri in iris}
        )
        if len(schemes) < artifacts.DIMENSION_COUNT:
            msg = (
                f"this evidence is annotated against {len(schemes)} taxonomy scheme(s) "
                f"and a map needs {artifacts.DIMENSION_COUNT}"
            )
            raise NotEnoughSchemes(msg)

        prediction = TaxonomySchemeDimensionGenerator()(
            user_query=UserQuery(query=ctx.research_session.question),
            indexed_vocab=indexed,
            available_schemes=schemes,
        )
        dimensions = [
            prediction.dimension1,
            prediction.dimension2,
            prediction.dimension3,
        ]
        version = ctx.write_artifact(
            artifacts.DIMENSIONS,
            artifacts.Dimensions(dimensions=dimensions, reasoning=prediction.reasoning),
        )

        rows = []
        for destiny_id, iris in annotations.items():
            coordinate = _coordinate(iris, by_iri, dimensions)
            if coordinate is None:
                continue
            rows.append(
                CoordinateRow(
                    destiny_id=destiny_id,
                    coordinate=coordinate,
                    reasoning=prediction.reasoning,
                    dimensions_version=version,
                )
            )
        ctx.set_coordinates(rows)
        return {
            "mapped": len(rows),
            "dropped": len(annotations) - len(rows),
            "version": version,
        }


def _coordinate(
    iris: list[IRI],
    by_iri: dict[str, Concept],
    dimensions: list[MappingDimensionWithSubTopics],
) -> dict[str, list[str]] | None:
    """A reference's concept labels per dimension, or None if it misses any of them."""
    coordinate = {}
    for dimension in dimensions:
        labels = list(
            dict.fromkeys(
                by_iri[iri].label
                for iri in iris
                if by_iri[iri].scheme == dimension.name
            )
        )
        if not labels:
            return None
        coordinate[dimension.name] = labels
    return coordinate
