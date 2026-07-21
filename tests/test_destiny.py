import uuid
from unittest.mock import MagicMock

from destiny_sdk.enhancements import EnhancementType

from research_mapper.destiny import evidence_from_destiny_reference

from conftest import _make_mock_reference


def test_evidence_from_reference_full(mock_reference):
    evidence = evidence_from_destiny_reference(mock_reference)

    assert evidence.destiny_id == mock_reference.id
    assert evidence.external_identifiers[0].identifier == "10.1000/test.doi"
    assert evidence.title == "Test Paper Title"
    assert evidence.authors == ["Author One", "Author Two"]
    assert evidence.year == 2023
    assert evidence.abstract == "This is a test abstract."
    assert evidence.pdf_urls == ["https://example.com/paper.pdf"]


def test_evidence_from_reference_no_enhancements():
    ref = MagicMock()
    ref.id = uuid.uuid4()
    ref.identifiers = []
    ref.enhancements = []

    evidence = evidence_from_destiny_reference(ref)

    assert evidence.destiny_id == ref.id
    assert evidence.external_identifiers == []
    assert evidence.title is None
    assert evidence.authors == []
    assert evidence.year is None
    assert evidence.abstract is None
    assert evidence.pdf_urls == []


def test_evidence_from_reference_location_without_pdf():
    """Locations with pdf_url=None should be silently skipped."""
    mock_location = MagicMock()
    mock_location.pdf_url = None

    location_content = MagicMock()
    location_content.enhancement_type = EnhancementType.LOCATION
    location_content.locations = [mock_location]

    location_enhancement = MagicMock()
    location_enhancement.content = location_content

    ref = MagicMock()
    ref.id = uuid.uuid4()
    ref.identifiers = []
    ref.enhancements = [location_enhancement]

    evidence = evidence_from_destiny_reference(ref)
    assert evidence.pdf_urls == []


def test_evidence_from_reference_preserves_doi_for_hash_deduplication():
    """Parsed identifiers must round-trip correctly for Evidence's hash-based dedup to work."""
    ref_id = uuid.uuid4()
    ref_a = _make_mock_reference(ref_id=ref_id, doi="10.1000/same")
    ref_b = _make_mock_reference(ref_id=ref_id, doi="10.1000/same")

    ev_a = evidence_from_destiny_reference(ref_a)
    ev_b = evidence_from_destiny_reference(ref_b)

    assert {ev_a, ev_b} == {ev_a}
