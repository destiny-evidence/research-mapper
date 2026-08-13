"""Tests for RIS export functionality."""

import io
import uuid

import rispy

from destiny_sdk.enhancements import Pagination, PublicationVenue, PublicationVenueType
from destiny_sdk.identifiers import DOIIdentifier, PubMedIdentifier

from research_mapper.export import export_evidence_to_ris, mapped_evidence_to_ris_entry
from research_mapper.models.common import Evidence
from research_mapper.models.mapping import MappedEvidence


def _make_evidence(**kwargs) -> Evidence:
    defaults = {
        "destiny_id": uuid.uuid4(),
        "title": "Test Paper",
        "abstract": "A test abstract.",
        "authors": ["Smith, J.", "Jones, A."],
        "year": 2024,
    }
    return Evidence(**(defaults | kwargs))


def _export_and_parse(evidences: list[Evidence]) -> list[dict]:
    buf = io.StringIO()
    export_evidence_to_ris(evidences, buf)
    buf.seek(0)
    return rispy.load(buf)


def test_basic_fields():
    ev = _make_evidence()
    (entry,) = _export_and_parse([ev])

    assert entry["title"] == "Test Paper"
    assert entry["abstract"] == "A test abstract."
    assert entry["authors"] == ["Smith, J.", "Jones, A."]
    assert entry["year"] == "2024"
    assert entry["id"] == str(ev.destiny_id)


def test_type_of_reference_defaults_to_gen():
    ev = _make_evidence()
    (entry,) = _export_and_parse([ev])
    assert entry["type_of_reference"] == "GEN"


def test_type_of_reference_from_venue_type():
    ev = _make_evidence(
        publication_venue=PublicationVenue(venue_type=PublicationVenueType.JOURNAL)
    )
    (entry,) = _export_and_parse([ev])
    assert entry["type_of_reference"] == "JOUR"


def test_publication_venue_fields():
    ev = _make_evidence(
        publication_venue=PublicationVenue(
            display_name="Nature Medicine",
            venue_type=PublicationVenueType.JOURNAL,
            issn=["1078-8956", "1546-170X"],
        )
    )
    (entry,) = _export_and_parse([ev])
    assert entry["journal_name"] == "Nature Medicine"
    assert entry["issn"] == "1078-8956"


def test_pagination_fields():
    ev = _make_evidence(
        pagination=Pagination(volume="12", issue="3", first_page="100", last_page="110")
    )
    (entry,) = _export_and_parse([ev])
    assert entry["volume"] == "12"
    assert entry["number"] == "3"
    assert entry["start_page"] == "100"
    assert entry["end_page"] == "110"


def test_doi_extracted_from_external_identifiers():
    ev = _make_evidence(
        external_identifiers=[DOIIdentifier(identifier="10.1000/test.doi")]
    )
    (entry,) = _export_and_parse([ev])
    assert entry["doi"] == "10.1000/test.doi"


def test_pubmed_id_extracted_as_accession_number():
    ev = _make_evidence(external_identifiers=[PubMedIdentifier(identifier=12345678)])
    (entry,) = _export_and_parse([ev])
    assert entry["accession_number"] == "12345678"


def test_landing_page_url_preferred_over_pdf_url():
    ev = _make_evidence(
        landing_page_urls=["https://doi.org/10.1000/test"],
        pdf_urls=["https://example.com/paper.pdf"],
    )
    (entry,) = _export_and_parse([ev])
    assert entry["urls"] == ["https://doi.org/10.1000/test"]


def test_pdf_url_used_when_no_landing_page():
    ev = _make_evidence(pdf_urls=["https://example.com/paper.pdf"])
    (entry,) = _export_and_parse([ev])
    assert entry["urls"] == ["https://example.com/paper.pdf"]


def test_multiple_evidences_exported():
    evs = [_make_evidence(title=f"Paper {i}") for i in range(3)]
    entries = _export_and_parse(evs)
    assert len(entries) == 3
    assert [e["title"] for e in entries] == ["Paper 0", "Paper 1", "Paper 2"]


def test_export_to_ris_writes_valid_file(tmp_path):
    evs = [_make_evidence(title="Paper A"), _make_evidence(title="Paper B")]
    out = tmp_path / "results.ris"
    with out.open("w", encoding="utf-8") as f:
        export_evidence_to_ris(evs, f)
    with out.open(encoding="utf-8") as f:
        entries = rispy.load(f)
    assert len(entries) == 2
    assert [e["title"] for e in entries] == ["Paper A", "Paper B"]


def test_optional_fields_absent_when_none():
    ev = _make_evidence()  # no publisher, venue, pagination, identifiers, urls
    (entry,) = _export_and_parse([ev])
    assert "publisher" not in entry
    assert "journal_name" not in entry
    assert "doi" not in entry
    assert "urls" not in entry


def test_mapped_evidence_flattens_multi_value_coordinate_into_separate_keywords():
    """A dimension with multiple subtopics (e.g. an evidence item annotated with
    multiple taxonomy concepts in one scheme) must produce one keyword per subtopic,
    not one keyword per dimension."""
    item = MappedEvidence(
        evidence=_make_evidence(),
        coordinate={"Theme": ["Access", "Equity"], "Design": ["RCT"]},
    )
    entry = mapped_evidence_to_ris_entry(item)
    assert entry["keywords"] == ["Theme: Access", "Theme: Equity", "Design: RCT"]
