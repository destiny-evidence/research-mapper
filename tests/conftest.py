import uuid
from unittest.mock import MagicMock

import pytest
from destiny_sdk.enhancements import EnhancementType


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: end-to-end tests requiring live .env credentials"
    )


def _make_mock_reference(
    ref_id=None,
    doi="10.1000/test.doi",
    title="Test Paper Title",
    authors=("Author One", "Author Two"),
    year=2023,
    abstract_text="This is a test abstract.",
    pdf_url="https://example.com/paper.pdf",
):
    """Build a MagicMock shaped like a destiny_sdk Reference."""
    ref_id = ref_id or uuid.uuid4()

    # identifier
    mock_identifier = MagicMock()
    mock_identifier.identifier = doi

    # BIBLIOGRAPHIC enhancement
    mock_author_1 = MagicMock()
    mock_author_1.display_name = authors[0]
    mock_author_2 = MagicMock()
    mock_author_2.display_name = authors[1]

    biblio_content = MagicMock()
    biblio_content.enhancement_type = EnhancementType.BIBLIOGRAPHIC
    biblio_content.title = title
    biblio_content.publication_year = year
    biblio_content.authorship = [mock_author_1, mock_author_2]

    biblio_enhancement = MagicMock()
    biblio_enhancement.content = biblio_content

    # ABSTRACT enhancement
    abstract_content = MagicMock()
    abstract_content.enhancement_type = EnhancementType.ABSTRACT
    abstract_content.abstract = abstract_text

    abstract_enhancement = MagicMock()
    abstract_enhancement.content = abstract_content

    # LOCATION enhancement
    mock_location = MagicMock()
    mock_location.pdf_url = pdf_url

    location_content = MagicMock()
    location_content.enhancement_type = EnhancementType.LOCATION
    location_content.locations = [mock_location]

    location_enhancement = MagicMock()
    location_enhancement.content = location_content

    ref = MagicMock()
    ref.id = ref_id
    ref.identifiers = [mock_identifier]
    ref.enhancements = [biblio_enhancement, abstract_enhancement, location_enhancement]

    return ref


@pytest.fixture
def mock_reference():
    return _make_mock_reference()


@pytest.fixture
def mock_destiny_client(mock_reference):
    mock_search_result = MagicMock()
    mock_search_result.references = [mock_reference]

    client = MagicMock()
    client.search.return_value = mock_search_result
    client.lookup.return_value = [mock_reference]

    return client
