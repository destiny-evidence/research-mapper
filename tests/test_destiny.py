import uuid
from unittest.mock import MagicMock

from destiny_sdk.enhancements import EnhancementType

from research_mapper.destiny import (
    _extract_concept_iris,
    evidence_from_destiny_reference,
)

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


# ---------------------------------------------------------------------------
# _extract_concept_iris — best-effort extraction of concept IRIs from a
# LinkedDataEnhancement's JSON-LD graph. Structure below is a trimmed-down stand-in
# for the real (much larger) DESTINY LinkedDataEnhancement shape confirmed live:
# Investigation -> Finding -> <field>.codedValue.@id (a compact IRI referencing a
# taxonomy concept), alongside blank nodes and plain literals that must be ignored.
# ---------------------------------------------------------------------------

_LINKED_DATA_CONTEXT = {
    "esea": "https://vocab.esea.education/",
    "hasFinding": {"@id": "esea:hasFinding"},
    "attrition": {"@id": "esea:attrition", "@type": "@id"},
    "educationTheme": {"@id": "esea:educationTheme", "@type": "@id"},
    "score": {"@id": "esea:score"},
}


def _linked_data_sample() -> dict:
    return {
        "@context": _LINKED_DATA_CONTEXT,
        "@type": "Investigation",
        "hasFinding": {
            "@id": "_:finding1",
            "@type": "Finding",
            "attrition": {"@id": "_:blank_attrition"},
            "educationTheme": {"@id": "esea:EducationThemeScheme/C00082"},
            "score": 7.27,
        },
    }


def test_extract_concept_iris_finds_nested_concept_reference():
    result = _extract_concept_iris(_linked_data_sample())
    assert result == {"https://vocab.esea.education/EducationThemeScheme/C00082"}


def test_extract_concept_iris_excludes_blank_nodes():
    """Blank node ids (_:finding1, _:blank_attrition) aren't concept references."""
    result = _extract_concept_iris(_linked_data_sample())
    assert not any(iri.startswith("_:") for iri in result)


def test_extract_concept_iris_ignores_plain_literals():
    """A plain numeric/string value (score: 7.27) produces no @id, so isn't collected."""
    data = {
        "@context": {"esea": "https://vocab.esea.education/", "score": "esea:score"},
        "score": 7.27,
    }
    assert _extract_concept_iris(data) == set()


def test_extract_concept_iris_degrades_to_empty_set_on_malformed_data():
    """
    Regression test: a malformed/unreachable @context must not break evidence
    conversion — degrade to no known concepts for this enhancement instead.
    """
    data = {"@context": "https://not-a-real-host.invalid/context.jsonld", "foo": "bar"}
    assert _extract_concept_iris(data) == set()


def test_evidence_from_reference_collects_known_concepts_from_linked_data():
    linked_data_content = MagicMock()
    linked_data_content.enhancement_type = EnhancementType.LINKED_DATA
    linked_data_content.data = _linked_data_sample()

    linked_data_enhancement = MagicMock()
    linked_data_enhancement.content = linked_data_content

    ref = MagicMock()
    ref.id = uuid.uuid4()
    ref.identifiers = []
    ref.enhancements = [linked_data_enhancement]

    evidence = evidence_from_destiny_reference(ref)

    assert evidence.known_concepts == [
        "https://vocab.esea.education/EducationThemeScheme/C00082"
    ]


def test_evidence_from_reference_unions_known_concepts_across_enhancements():
    """Multiple linked_data enhancements (e.g. different vocab versions) are unioned."""

    def _make_linked_data_enhancement(concept_iri: str):
        content = MagicMock()
        content.enhancement_type = EnhancementType.LINKED_DATA
        content.data = {
            "@context": {
                "esea": "https://vocab.esea.education/",
                "educationTheme": {"@id": "esea:educationTheme", "@type": "@id"},
            },
            "educationTheme": {"@id": concept_iri},
        }
        enhancement = MagicMock()
        enhancement.content = content
        return enhancement

    ref = MagicMock()
    ref.id = uuid.uuid4()
    ref.identifiers = []
    ref.enhancements = [
        _make_linked_data_enhancement("https://vocab.esea.education/A/C1"),
        _make_linked_data_enhancement("https://vocab.esea.education/B/C2"),
    ]

    evidence = evidence_from_destiny_reference(ref)

    assert set(evidence.known_concepts) == {
        "https://vocab.esea.education/A/C1",
        "https://vocab.esea.education/B/C2",
    }
