import uuid

import pytest

from research_mapper.models import Evidence, LuceneQuery, UserQuery

from conftest import _make_mock_reference


# ---------------------------------------------------------------------------
# UserQuery
# ---------------------------------------------------------------------------


def test_user_query_stores_text():
    q = UserQuery(query="what causes climate change")
    assert q.query == "what causes climate change"


# ---------------------------------------------------------------------------
# LuceneQuery validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query_str",
    [
        "climate AND health",
        "title:cancer",
        "author:smith AND year:[2020 TO 2024]",
        "simple",
        '"exact phrase"',
    ],
)
def test_lucene_query_valid(query_str):
    lq = LuceneQuery(query=query_str)
    assert lq.query == query_str


@pytest.mark.parametrize(
    "bad_query",
    [
        "AND OR",
        "((unclosed",
        "field::double_colon",
    ],
)
def test_lucene_query_invalid_syntax_raises(bad_query):
    with pytest.raises(ValueError, match="Invalid Lucene syntax"):
        LuceneQuery(query=bad_query)


# ---------------------------------------------------------------------------
# Evidence.from_destiny_reference
# ---------------------------------------------------------------------------


def test_evidence_from_reference_full(mock_reference):
    evidence = Evidence.from_destiny_reference(mock_reference)

    assert evidence.destiny_id == mock_reference.id
    assert evidence.external_identifiers[0].identifier == "10.1000/test.doi"
    assert evidence.title == "Test Paper Title"
    assert evidence.authors == ["Author One", "Author Two"]
    assert evidence.year == 2023
    assert evidence.abstract == "This is a test abstract."
    assert evidence.pdf_urls == ["https://example.com/paper.pdf"]


def test_evidence_from_reference_no_enhancements():
    from unittest.mock import MagicMock

    ref = MagicMock()
    ref.id = uuid.uuid4()
    ref.identifiers = []
    ref.enhancements = []

    evidence = Evidence.from_destiny_reference(ref)

    assert evidence.destiny_id == ref.id
    assert evidence.external_identifiers == []
    assert evidence.title is None
    assert evidence.authors == []
    assert evidence.year is None
    assert evidence.abstract is None
    assert evidence.pdf_urls == []


def test_evidence_from_reference_location_without_pdf():
    """Locations with pdf_url=None should be silently skipped."""
    from unittest.mock import MagicMock
    from destiny_sdk.enhancements import EnhancementType

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

    evidence = Evidence.from_destiny_reference(ref)
    assert evidence.pdf_urls == []


# ---------------------------------------------------------------------------
# Evidence.__hash__ deduplication
# ---------------------------------------------------------------------------


def test_evidence_hash_deduplication():
    ref_id = uuid.uuid4()
    ref_a = _make_mock_reference(ref_id=ref_id, doi="10.1000/same")
    ref_b = _make_mock_reference(ref_id=ref_id, doi="10.1000/same")

    ev_a = Evidence.from_destiny_reference(ref_a)
    ev_b = Evidence.from_destiny_reference(ref_b)

    result = {ev_a, ev_b}
    assert len(result) == 1


def test_evidence_hash_different_ids():
    ev_a = Evidence.from_destiny_reference(_make_mock_reference(ref_id=uuid.uuid4()))
    ev_b = Evidence.from_destiny_reference(_make_mock_reference(ref_id=uuid.uuid4()))

    result = {ev_a, ev_b}
    assert len(result) == 2


def test_evidences_with_same_hash_are_equal():
    ref_id = uuid.uuid4()
    ref_a = _make_mock_reference(ref_id=ref_id, doi="10.1000/same")
    ref_b = _make_mock_reference(ref_id=ref_id, doi="10.1000/same")

    ev_a = Evidence.from_destiny_reference(ref_a)
    ev_b = Evidence.from_destiny_reference(ref_b)

    assert hash(ev_a) == hash(ev_b)
    assert ev_a == ev_b


def test_evidences_with_different_hash_are_not_equal():
    ev_a = Evidence.from_destiny_reference(_make_mock_reference(ref_id=uuid.uuid4()))
    ev_b = Evidence.from_destiny_reference(_make_mock_reference(ref_id=uuid.uuid4()))

    assert hash(ev_a) != hash(ev_b)
    assert ev_a != ev_b


def test_evidence_to_str_uses_destiny_id_when_no_title_or_abstract_available():
    destiny_id = uuid.uuid4()
    ev_a = Evidence(
        destiny_id=destiny_id,
    )

    assert str(ev_a) == str(destiny_id)


def test_evidence_to_str_uses_title_when_only_title_available():
    title = "This is a paper!"
    ev_a = Evidence(
        destiny_id=uuid.uuid4(),
        title=title,
    )

    assert str(ev_a) == f"{title} - "


def test_evidence_to_str_uses_abstract_when_only_abstract_available():
    abstract = "This is an important abstract!"
    ev_a = Evidence(
        destiny_id=uuid.uuid4(),
        abstract=abstract,
    )

    assert str(ev_a) == f" - {abstract}"


def test_evidence_to_str_uses_title_andabstract_when_both_available():
    title = "This is a paper!"
    abstract = "This is an important abstract!"
    ev_a = Evidence(destiny_id=uuid.uuid4(), title=title, abstract=abstract)

    assert str(ev_a) == f"{title} - {abstract}"
