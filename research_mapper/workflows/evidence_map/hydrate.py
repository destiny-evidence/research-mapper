from collections.abc import Generator, Sequence
from uuid import UUID

from destiny_sdk.identifiers import IdentifierLookup

from research_mapper.config import get_destiny_client
from research_mapper.destiny import evidence_from_destiny_reference
from research_mapper.models.common import Evidence

DESTINY_LOOKUP_CHUNK_SIZE = 100


def get_references(reference_ids: Sequence[UUID]) -> Generator[dict[UUID, Evidence]]:
    """Generates pages of evidence from DESTINY reference ids."""
    client = get_destiny_client()
    for start in range(0, len(reference_ids), DESTINY_LOOKUP_CHUNK_SIZE):
        references = client.lookup(
            [
                IdentifierLookup.from_identifier(reference_id)
                for reference_id in reference_ids[
                    start : start + DESTINY_LOOKUP_CHUNK_SIZE
                ]
            ],
            timeout=30,
        )
        yield {
            reference.id: evidence_from_destiny_reference(reference)
            for reference in references
        }
